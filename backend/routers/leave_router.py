# =============================================================================
# AttendTrax Enterprise – Leave & Permission Workflow Router
# routers/leave_router.py  –  Faculty Leaves & Student Dual-Track Approval Queues
# =============================================================================
import uuid
import secrets
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import (
    User, Student, ClassRoom, Department, FacultyLeave, 
    StudentLeave, HostelGatePass, Notification, AuditLog
)

router = APIRouter(prefix="/leaves", tags=["Leaves & Permissions"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class FacultyLeaveApplyRequest(BaseModel):
    leave_category: str = "CASUAL"          # CASUAL, MEDICAL, ON_DUTY, PERMISSION, EARNED
    session_scope: str = "FULL_DAY"         # FULL_DAY, FN_HALF_DAY, AN_HALF_DAY, SPECIFIC_HOURS
    start_date: date
    end_date: date
    specific_time_window: Optional[str] = None # e.g. "09:00-10:30"
    reason: str
    attachment_url: Optional[str] = None


class ReviewLeaveRequest(BaseModel):
    action: str                             # "APPROVE" or "REJECT"
    remarks: Optional[str] = ""


class StudentLeaveApplyRequest(BaseModel):
    leave_type: str = "CASUAL"              # CASUAL, MEDICAL, ON_DUTY, GATE_PASS
    start_date: date
    end_date: date
    reason: str
    attachment_url: Optional[str] = None


class GateVerificationRequest(BaseModel):
    pass_token: str
    action: str                             # "EXIT" or "RETURN"
    security_officer_name: Optional[str] = "Main Gate Security"


# ═════════════════════════════════════════════════════════════════════════════
# 1. FACULTY LEAVE WORKFLOW (Faculty -> HOD -> Principal/VP)
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/faculty/apply")
async def faculty_apply_leave(
    body: FacultyLeaveApplyRequest,
    current_user: dict = Depends(require_role("FACULTY", "CLASS_INCHARGE", "DEPT_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Faculty submits leave or short permission application."""
    user_id = current_user.get("user_id")
    dept_id = current_user.get("department_id")

    # If department_id not in JWT, query from user table
    if not dept_id:
        u_stmt = select(User.department_id).where(User.username == current_user.get("sub"))
        u_res = await db.execute(u_stmt)
        dept_id = u_res.scalar_one_or_none() or 1

    leave_app = FacultyLeave(
        faculty_id=user_id or 1,
        department_id=dept_id,
        leave_category=body.leave_category.upper(),
        session_scope=body.session_scope.upper(),
        start_date=body.start_date,
        end_date=body.end_date,
        specific_time_window=body.specific_time_window,
        reason=body.reason.strip(),
        attachment_url=body.attachment_url,
        hod_status="PENDING",
        principal_status="PENDING",
        final_status="PENDING",
    )
    db.add(leave_app)
    await db.flush()

    # Log audit
    audit = AuditLog(
        user_id=user_id,
        action="FACULTY_LEAVE_APPLY",
        target_entity="FacultyLeave",
        target_id=leave_app.id,
        new_values={"category": body.leave_category, "scope": body.session_scope, "start": str(body.start_date)},
    )
    db.add(audit)
    await db.commit()

    return {
        "message": f"Leave application for {body.session_scope} submitted successfully. Routed to HOD for Level 1 review.",
        "leave_id": leave_app.id,
        "status": "PENDING",
    }


@router.get("/faculty/my-leaves")
async def get_my_faculty_leaves(
    current_user: dict = Depends(require_role("FACULTY", "CLASS_INCHARGE", "DEPT_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Return all leave applications raised by the logged-in faculty member."""
    user_id = current_user.get("user_id")
    stmt = select(FacultyLeave).where(FacultyLeave.faculty_id == user_id).order_by(desc(FacultyLeave.created_at))
    res = await db.execute(stmt)
    records = res.scalars().all()
    return records


@router.get("/faculty/pending-hod")
async def get_faculty_leaves_pending_hod(
    current_user: dict = Depends(require_role("DEPT_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Department HOD views faculty leave tickets awaiting Level 1 review."""
    dept_id = current_user.get("department_id")
    stmt = select(FacultyLeave, User.full_name, User.username).join(
        User, FacultyLeave.faculty_id == User.id
    ).where(
        FacultyLeave.hod_status == "PENDING"
    ).order_by(FacultyLeave.created_at)

    if current_user.get("role") == "DEPT_ADMIN" and dept_id:
        stmt = stmt.where(FacultyLeave.department_id == dept_id)

    res = await db.execute(stmt)
    rows = res.all()
    return [
        {
            "id": r.FacultyLeave.id,
            "faculty_name": r.full_name,
            "faculty_username": r.username,
            "leave_category": r.FacultyLeave.leave_category,
            "session_scope": r.FacultyLeave.session_scope,
            "start_date": r.FacultyLeave.start_date,
            "end_date": r.FacultyLeave.end_date,
            "specific_time_window": r.FacultyLeave.specific_time_window,
            "reason": r.FacultyLeave.reason,
            "attachment_url": r.FacultyLeave.attachment_url,
            "created_at": r.FacultyLeave.created_at,
            "hod_status": r.FacultyLeave.hod_status,
        }
        for r in rows
    ]


@router.patch("/faculty/{leave_id}/hod-review")
async def hod_review_faculty_leave(
    leave_id: int,
    body: ReviewLeaveRequest,
    current_user: dict = Depends(require_role("DEPT_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """HOD approves or rejects faculty leave. If approved, advances to Principal/VP review."""
    stmt = select(FacultyLeave).where(FacultyLeave.id == leave_id)
    res = await db.execute(stmt)
    leave = res.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Faculty leave ticket not found.")

    act = body.action.upper()
    user_id = current_user.get("user_id")

    if act == "APPROVE":
        leave.hod_status = "APPROVED"
        leave.hod_remarks = body.remarks or "Recommended by HOD"
        leave.hod_action_at = datetime.utcnow()
        leave.hod_user_id = user_id
        leave.final_status = "HOD_APPROVED"
        msg = "Faculty leave recommended by HOD. Routed to Principal for final approval."
    else:
        leave.hod_status = "REJECTED"
        leave.hod_remarks = body.remarks or "Rejected by HOD"
        leave.hod_action_at = datetime.utcnow()
        leave.hod_user_id = user_id
        leave.final_status = "REJECTED"
        msg = "Faculty leave rejected by HOD."

    # Notify faculty
    notif = Notification(
        user_id=leave.faculty_id,
        title=f"Leave Application Update ({leave.session_scope})",
        message=f"HOD has {act.lower()}ed your leave request. {leave.hod_remarks}",
        action_url="/faculty.html#leave",
    )
    db.add(notif)
    await db.commit()
    return {"message": msg, "leave_id": leave_id, "status": leave.final_status}


@router.get("/faculty/pending-principal")
async def get_faculty_leaves_pending_principal(
    current_user: dict = Depends(require_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin (Principal / Vice Principal) views HOD-recommended leaves for final sign-off."""
    stmt = select(
        FacultyLeave, User.full_name, User.username, Department.code.label("dept_code")
    ).join(
        User, FacultyLeave.faculty_id == User.id
    ).join(
        Department, FacultyLeave.department_id == Department.id
    ).where(
        and_(FacultyLeave.hod_status == "APPROVED", FacultyLeave.principal_status == "PENDING")
    ).order_by(FacultyLeave.created_at)

    res = await db.execute(stmt)
    rows = res.all()
    return [
        {
            "id": r.FacultyLeave.id,
            "faculty_name": r.full_name,
            "faculty_username": r.username,
            "department": r.dept_code,
            "leave_category": r.FacultyLeave.leave_category,
            "session_scope": r.FacultyLeave.session_scope,
            "start_date": r.FacultyLeave.start_date,
            "end_date": r.FacultyLeave.end_date,
            "specific_time_window": r.FacultyLeave.specific_time_window,
            "reason": r.FacultyLeave.reason,
            "hod_remarks": r.FacultyLeave.hod_remarks,
            "created_at": r.FacultyLeave.created_at,
        }
        for r in rows
    ]


@router.patch("/faculty/{leave_id}/principal-review")
async def principal_review_faculty_leave(
    leave_id: int,
    body: ReviewLeaveRequest,
    current_user: dict = Depends(require_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Principal / Vice Principal grants final executive approval or rejection."""
    stmt = select(FacultyLeave).where(FacultyLeave.id == leave_id)
    res = await db.execute(stmt)
    leave = res.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Faculty leave ticket not found.")

    act = body.action.upper()
    user_id = current_user.get("user_id")

    if act == "APPROVE":
        leave.principal_status = "APPROVED"
        leave.principal_remarks = body.remarks or "Approved by Principal"
        leave.principal_action_at = datetime.utcnow()
        leave.principal_user_id = user_id
        leave.final_status = "APPROVED"
        msg = "Faculty leave granted full executive approval by Principal. Notification sent."
    else:
        leave.principal_status = "REJECTED"
        leave.principal_remarks = body.remarks or "Rejected by Principal"
        leave.principal_action_at = datetime.utcnow()
        leave.principal_user_id = user_id
        leave.final_status = "REJECTED"
        msg = "Faculty leave rejected by Principal."

    # Send Notification to Faculty
    notif = Notification(
        user_id=leave.faculty_id,
        title=f"Official Leave Decision: {leave.final_status}",
        message=f"Principal has {act.lower()}ed your leave request ({leave.session_scope}). {leave.principal_remarks}",
        action_url="/faculty.html#leave",
    )
    db.add(notif)
    await db.commit()
    return {"message": msg, "leave_id": leave_id, "status": leave.final_status}


# ═════════════════════════════════════════════════════════════════════════════
# 2. DUAL-TRACK STUDENT LEAVE & OUTPASS WORKFLOW
#    (Day Scholar: Incharge -> HOD)
#    (Hosteller: Incharge -> HOD -> Warden)
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/student/apply")
async def student_apply_leave(
    body: StudentLeaveApplyRequest,
    current_user: dict = Depends(require_role("STUDENT")),
    db: AsyncSession = Depends(get_db),
):
    """Student submits leave or hostel outpass application."""
    user_id = current_user.get("user_id")
    # Fetch Student profile
    s_stmt = select(Student).where(Student.user_id == user_id)
    s_res = await db.execute(s_stmt)
    student = s_res.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    is_hosteller = (student.residence_type == "HOSTELLER")

    leave_app = StudentLeave(
        student_id=student.id,
        class_id=student.class_id,
        department_id=student.department_id,
        residence_type=student.residence_type,
        leave_type=body.leave_type.upper(),
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason.strip(),
        attachment_url=body.attachment_url,
        incharge_status="PENDING",
        hod_status="PENDING",
        warden_status="PENDING" if is_hosteller else "NOT_APPLICABLE",
        final_status="PENDING",
    )
    db.add(leave_app)
    await db.flush()

    audit = AuditLog(
        user_id=user_id,
        action="STUDENT_LEAVE_APPLY",
        target_entity="StudentLeave",
        target_id=leave_app.id,
        new_values={"type": student.residence_type, "start": str(body.start_date), "end": str(body.end_date)},
    )
    db.add(audit)
    await db.commit()

    queue_desc = "Class Incharge -> HOD -> Hostel Warden" if is_hosteller else "Class Incharge -> HOD"
    return {
        "message": f"Leave application submitted. Routed to approval queue ({queue_desc}).",
        "leave_id": leave_app.id,
        "residence_type": student.residence_type,
        "status": "PENDING",
    }


@router.get("/student/my-leaves")
async def get_my_student_leaves(
    current_user: dict = Depends(require_role("STUDENT")),
    db: AsyncSession = Depends(get_db),
):
    """Return all leave and outpass tickets raised by the logged-in student."""
    user_id = current_user.get("user_id")
    s_stmt = select(Student.id).where(Student.user_id == user_id)
    s_res = await db.execute(s_stmt)
    student_id = s_res.scalar_one_or_none()
    if not student_id:
        return []

    stmt = select(StudentLeave, HostelGatePass.pass_token, HostelGatePass.pass_status).outerjoin(
        HostelGatePass, StudentLeave.id == HostelGatePass.leave_id
    ).where(
        StudentLeave.student_id == student_id
    ).order_by(desc(StudentLeave.created_at))

    res = await db.execute(stmt)
    results = []
    for row in res.all():
        l = row.StudentLeave
        results.append({
            "id": l.id,
            "leave_type": l.leave_type,
            "residence_type": l.residence_type,
            "start_date": l.start_date,
            "end_date": l.end_date,
            "reason": l.reason,
            "incharge_status": l.incharge_status,
            "hod_status": l.hod_status,
            "warden_status": l.warden_status,
            "final_status": l.final_status,
            "pass_token": row.pass_token,
            "pass_status": row.pass_status,
            "created_at": l.created_at,
        })
    return results


@router.get("/student/pending-incharge")
async def get_student_leaves_pending_incharge(
    current_user: dict = Depends(require_role("CLASS_INCHARGE", "FACULTY", "DEPT_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Class Incharge views pending student leave tickets for their class."""
    stmt = select(
        StudentLeave, Student.name, Student.reg_no, ClassRoom.class_code
    ).join(
        Student, StudentLeave.student_id == Student.id
    ).join(
        ClassRoom, StudentLeave.class_id == ClassRoom.id
    ).where(
        StudentLeave.incharge_status == "PENDING"
    ).order_by(StudentLeave.created_at)

    res = await db.execute(stmt)
    return [
        {
            "id": r.StudentLeave.id,
            "student_name": r.name,
            "reg_no": r.reg_no,
            "class_code": r.class_code,
            "residence_type": r.StudentLeave.residence_type,
            "leave_type": r.StudentLeave.leave_type,
            "start_date": r.StudentLeave.start_date,
            "end_date": r.StudentLeave.end_date,
            "reason": r.StudentLeave.reason,
            "created_at": r.StudentLeave.created_at,
        }
        for r in res.all()
    ]


@router.patch("/student/{leave_id}/incharge-review")
async def incharge_review_student_leave(
    leave_id: int,
    body: ReviewLeaveRequest,
    current_user: dict = Depends(require_role("CLASS_INCHARGE", "FACULTY", "DEPT_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Class Incharge approves Level 1 $\rightarrow$ advances ticket to HOD."""
    stmt = select(StudentLeave).where(StudentLeave.id == leave_id)
    res = await db.execute(stmt)
    leave = res.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Student leave ticket not found.")

    act = body.action.upper()
    user_id = current_user.get("user_id")

    if act == "APPROVE":
        leave.incharge_status = "APPROVED"
        leave.incharge_remarks = body.remarks or "Recommended by Class Incharge"
        leave.incharge_action_at = datetime.utcnow()
        leave.incharge_user_id = user_id
        leave.final_status = "INCHARGE_APPROVED"
        msg = "Student leave verified and recommended by Class Incharge. Routed to HOD."
    else:
        leave.incharge_status = "REJECTED"
        leave.incharge_remarks = body.remarks or "Rejected by Class Incharge"
        leave.incharge_action_at = datetime.utcnow()
        leave.incharge_user_id = user_id
        leave.final_status = "REJECTED"
        msg = "Student leave rejected by Class Incharge."

    await db.commit()
    return {"message": msg, "leave_id": leave_id, "status": leave.final_status}


@router.get("/student/pending-hod")
async def get_student_leaves_pending_hod(
    current_user: dict = Depends(require_role("DEPT_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Department HOD views student leaves verified by Class Incharge."""
    dept_id = current_user.get("department_id")
    stmt = select(
        StudentLeave, Student.name, Student.reg_no, ClassRoom.class_code
    ).join(
        Student, StudentLeave.student_id == Student.id
    ).join(
        ClassRoom, StudentLeave.class_id == ClassRoom.id
    ).where(
        and_(StudentLeave.incharge_status == "APPROVED", StudentLeave.hod_status == "PENDING")
    ).order_by(StudentLeave.created_at)

    if current_user.get("role") == "DEPT_ADMIN" and dept_id:
        stmt = stmt.where(StudentLeave.department_id == dept_id)

    res = await db.execute(stmt)
    return [
        {
            "id": r.StudentLeave.id,
            "student_name": r.name,
            "reg_no": r.reg_no,
            "class_code": r.class_code,
            "residence_type": r.StudentLeave.residence_type,
            "leave_type": r.StudentLeave.leave_type,
            "start_date": r.StudentLeave.start_date,
            "end_date": r.StudentLeave.end_date,
            "reason": r.StudentLeave.reason,
            "incharge_remarks": r.StudentLeave.incharge_remarks,
            "created_at": r.StudentLeave.created_at,
        }
        for r in res.all()
    ]


@router.patch("/student/{leave_id}/hod-review")
async def hod_review_student_leave(
    leave_id: int,
    body: ReviewLeaveRequest,
    current_user: dict = Depends(require_role("DEPT_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """HOD reviews Level 2. If Day Scholar, marks final APPROVED; if Hosteller, routes to Hostel Warden."""
    stmt = select(StudentLeave).where(StudentLeave.id == leave_id)
    res = await db.execute(stmt)
    leave = res.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Student leave ticket not found.")

    act = body.action.upper()
    user_id = current_user.get("user_id")

    if act == "APPROVE":
        leave.hod_status = "APPROVED"
        leave.hod_remarks = body.remarks or "Approved by HOD"
        leave.hod_action_at = datetime.utcnow()
        leave.hod_user_id = user_id

        if leave.residence_type == "HOSTELLER":
            leave.final_status = "HOD_APPROVED"
            msg = "Leave approved by HOD. Routed to Hostel Warden for residential outpass approval."
        else:
            leave.final_status = "APPROVED"
            msg = "Day Scholar leave approved by HOD. Granted official leave permission."
    else:
        leave.hod_status = "REJECTED"
        leave.hod_remarks = body.remarks or "Rejected by HOD"
        leave.hod_action_at = datetime.utcnow()
        leave.hod_user_id = user_id
        leave.final_status = "REJECTED"
        msg = "Student leave rejected by HOD."

    await db.commit()
    return {"message": msg, "leave_id": leave_id, "status": leave.final_status}


@router.get("/student/pending-warden")
async def get_student_leaves_pending_warden(
    current_user: dict = Depends(require_role("WARDEN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Hostel Warden views hosteller leaves approved by HOD awaiting gate pass issuance."""
    stmt = select(
        StudentLeave, Student.name, Student.reg_no, Student.hostel_block_room, ClassRoom.class_code
    ).join(
        Student, StudentLeave.student_id == Student.id
    ).join(
        ClassRoom, StudentLeave.class_id == ClassRoom.id
    ).where(
        and_(
            StudentLeave.residence_type == "HOSTELLER",
            StudentLeave.hod_status == "APPROVED",
            StudentLeave.warden_status == "PENDING"
        )
    ).order_by(StudentLeave.created_at)

    res = await db.execute(stmt)
    return [
        {
            "id": r.StudentLeave.id,
            "student_name": r.name,
            "reg_no": r.reg_no,
            "class_code": r.class_code,
            "hostel_room": r.hostel_block_room or "Unassigned",
            "leave_type": r.StudentLeave.leave_type,
            "start_date": r.StudentLeave.start_date,
            "end_date": r.StudentLeave.end_date,
            "reason": r.StudentLeave.reason,
            "hod_remarks": r.StudentLeave.hod_remarks,
            "created_at": r.StudentLeave.created_at,
        }
        for r in res.all()
    ]


@router.patch("/student/{leave_id}/warden-review")
async def warden_review_student_leave(
    leave_id: int,
    body: ReviewLeaveRequest,
    current_user: dict = Depends(require_role("WARDEN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Hostel Warden approves Level 3 $\rightarrow$ generates digital QR Gatepass Token."""
    stmt = select(StudentLeave).where(StudentLeave.id == leave_id)
    res = await db.execute(stmt)
    leave = res.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Student leave ticket not found.")

    act = body.action.upper()
    user_id = current_user.get("user_id")

    if act == "APPROVE":
        leave.warden_status = "APPROVED"
        leave.warden_remarks = body.remarks or "Approved by Hostel Warden"
        leave.warden_action_at = datetime.utcnow()
        leave.warden_user_id = user_id
        leave.final_status = "APPROVED"

        # Generate Cryptographic Outpass Token
        token = secrets.token_hex(16).upper()
        pass_obj = HostelGatePass(
            leave_id=leave.id,
            student_id=leave.student_id,
            pass_token=token,
            qr_code_data=f"ATTENDTRAX-PASS:{token}:{leave.student_id}",
            valid_from=datetime.combine(leave.start_date, datetime.min.time()),
            valid_until=datetime.combine(leave.end_date, datetime.max.time()),
            pass_status="ISSUED",
        )
        db.add(pass_obj)
        msg = f"Hostel outpass approved! Digital Gate Token #{token} generated."
    else:
        leave.warden_status = "REJECTED"
        leave.warden_remarks = body.remarks or "Rejected by Hostel Warden"
        leave.warden_action_at = datetime.utcnow()
        leave.warden_user_id = user_id
        leave.final_status = "REJECTED"
        msg = "Hostel outpass rejected by Warden."

    await db.commit()
    return {"message": msg, "leave_id": leave_id, "status": leave.final_status}


@router.post("/gatepass/verify")
async def verify_gate_outpass(
    body: GateVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Main Gate Security scans QR token to record Exit or Return timestamp."""
    stmt = select(HostelGatePass, Student.name, Student.reg_no).join(
        Student, HostelGatePass.student_id == Student.id
    ).where(
        HostelGatePass.pass_token == body.pass_token.strip().upper()
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Invalid Gate Pass Token.")

    gp = row.HostelGatePass
    act = body.action.upper()
    now = datetime.utcnow()

    if act == "EXIT":
        gp.gate_exit_at = now
        gp.pass_status = "EXITED"
        gp.security_officer_name = body.security_officer_name
        msg = f"Recorded EXIT for {row.name} ({row.reg_no}) at {now.strftime('%H:%M:%S')}."
    elif act == "RETURN":
        gp.gate_return_at = now
        gp.pass_status = "RETURNED"
        msg = f"Recorded RETURN for {row.name} ({row.reg_no}) at {now.strftime('%H:%M:%S')}."
    else:
        raise HTTPException(status_code=400, detail="Action must be EXIT or RETURN.")

    await db.commit()
    return {
        "message": msg,
        "student_name": row.name,
        "reg_no": row.reg_no,
        "pass_status": gp.pass_status,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
