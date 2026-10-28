# =============================================================================
# routers/faculty_router.py  –  Faculty endpoints with Hybrid Dual-Engine Speed
# =============================================================================
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

import sheets
from database import get_db
from dependencies import require_role
from models import ClassRoom, Student, Subject, AttendanceSession, AttendanceRecord, User
from sheets import ALL_HOURS, HOUR_LABELS

router = APIRouter(prefix="/faculty", tags=["Faculty"])

_faculty_dep = Depends(require_role("FACULTY", "ADMIN", "CLASS_INCHARGE", "DEPT_ADMIN", "SUPER_ADMIN"))


# ── GET helpers (SQL-Accelerated with Sheets Fallback) ────────────────────────
@router.get("/classes")
async def list_classes(
    current_user: dict = _faculty_dep,
    db: AsyncSession = Depends(get_db),
):
    """Return all active classes with sub-millisecond SQL response."""
    try:
        stmt = select(ClassRoom).where(ClassRoom.status == "ACTIVE").order_by(ClassRoom.class_code)
        classes = (await db.execute(stmt)).scalars().all()
        if classes:
            return [
                {
                    "ClassID": c.class_code,
                    "ClassName": c.class_name,
                    "Year": str(c.year),
                    "Section": c.section,
                    "Semester": str(c.semester),
                    "Status": c.status,
                }
                for c in classes
            ]
    except Exception:
        pass
    return sheets.get_all_classes()


@router.get("/classes/{class_id}/subjects")
def list_subjects(class_id: str, current_user: dict = _faculty_dep):
    """Return subjects assigned to a class."""
    return sheets.get_subjects_for_class(class_id)


@router.get("/hours")
def list_hours(_=_faculty_dep):
    """Return hour labels."""
    return [{"value": k, "label": v} for k, v in HOUR_LABELS.items()]


@router.get("/classes/{class_id}/students")
async def list_students(
    class_id: str,
    _=_faculty_dep,
    db: AsyncSession = Depends(get_db),
):
    """Return students for attendance marking (SQL-accelerated)."""
    try:
        cls_stmt = select(ClassRoom.id).where(ClassRoom.class_code == class_id)
        cid = (await db.execute(cls_stmt)).scalar_one_or_none()
        if cid:
            st_stmt = select(Student).where(
                and_(Student.class_id == cid, Student.status == "ACTIVE")
            ).order_by(Student.reg_no)
            students = (await db.execute(st_stmt)).scalars().all()
            if students:
                return [{"reg_no": s.reg_no, "name": s.name} for s in students]
    except Exception:
        pass
    return sheets.get_students_for_attendance(class_id)


# ── Attendance submission (Instant SQL + Non-Blocking Sheets Sync) ───────────
class AttendanceEntry(BaseModel):
    reg_no: str
    status: str   # "P", "A", or "OD"


class SubmitAttendanceRequest(BaseModel):
    class_id: str
    subject_id: str
    hour: str = "DAY"   # Defaults to single daily attendance "DAY"
    attendance: List[AttendanceEntry]


def _background_sheets_sync(class_id: str, date_str: str, hour_val: str, subject_id: str, faculty_id: str, attendance_map: Dict[str, str]):
    """Background worker task to push attendance to Google Sheets without blocking HTTP client."""
    try:
        sheets.save_attendance(
            class_id=class_id,
            date_str=date_str,
            hour=hour_val,
            subject_id=subject_id,
            faculty_id=faculty_id,
            attendance=attendance_map,
        )
    except Exception as e:
        print(f"[Sheets Background Sync Notice] {e}")


@router.post("/attendance")
async def submit_attendance(
    body: SubmitAttendanceRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = _faculty_dep,
    db: AsyncSession = Depends(get_db),
):
    hour_val = (body.hour or "DAY").strip().upper()

    # Validate status values: "P" (Present), "A" (Absent), "OD" (On-Duty)
    for entry in body.attendance:
        st = entry.status.upper()
        if st not in ("P", "A", "OD", "-"):
            raise HTTPException(status_code=400, detail=f"Invalid status '{entry.status}'. Use P, A, or OD.")

    # Auto fetch today's date (IST)
    today_str = sheets.get_ist_today_str()
    today_date = date.today()

    # 1. Check immutability in SQL database
    cls_stmt = select(ClassRoom.id).where(ClassRoom.class_code == body.class_id)
    cid = (await db.execute(cls_stmt)).scalar_one_or_none()

    if cid:
        chk_stmt = select(AttendanceSession).where(
            and_(
                AttendanceSession.class_id == cid,
                AttendanceSession.session_date == today_date,
                AttendanceSession.slot_hour == hour_val
            )
        )
        if (await db.execute(chk_stmt)).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Attendance for {body.class_id} on {today_str} ({hour_val}) has already been submitted and is locked.",
            )

    faculty_id_str = str(current_user.get("UserID", ""))
    user_id = current_user.get("user_id")
    attendance_map: Dict[str, str] = {e.reg_no: e.status.upper() for e in body.attendance}

    # 2. Persist to SQL immediately
    if cid:
        new_session = AttendanceSession(
            class_id=cid,
            session_date=today_date,
            slot_hour=hour_val,
            session_type="DAILY" if hour_val in ("DAILY", "DAY") else "HOURLY",
            faculty_id=user_id or 1,
            lock_status="LOCKED"
        )
        db.add(new_session)
        await db.flush()

        # Batch insert student records
        st_stmt = select(Student).where(Student.class_id == cid)
        students = (await db.execute(st_stmt)).scalars().all()
        st_map = {s.reg_no: s.id for s in students}

        for rn, st_val in attendance_map.items():
            if rn in st_map:
                db.add(AttendanceRecord(
                    session_id=new_session.id,
                    student_id=st_map[rn],
                    status=st_val
                ))
        await db.commit()

    # 3. Queue non-blocking asynchronous sync to Google Sheets
    background_tasks.add_task(
        _background_sheets_sync,
        body.class_id,
        today_str,
        hour_val,
        body.subject_id,
        faculty_id_str,
        attendance_map,
    )

    return {
        "message": "Attendance saved successfully.",
        "date": today_str,
        "status": "CONFIRMED",
        "sync": "QUEUED_TO_CLOUD"
    }


# ── Check if slot already submitted (Instant SQL check) ──────────────────────
@router.get("/attendance/check")
async def check_slot(
    class_id: str,
    subject_id: str = "",
    hour: str = "DAY",
    _=_faculty_dep,
    db: AsyncSession = Depends(get_db),
):
    today_str = sheets.get_ist_today_str()
    today_date = date.today()
    hour_val = (hour or "DAY").strip().upper()

    try:
        cls_stmt = select(ClassRoom.id).where(ClassRoom.class_code == class_id)
        cid = (await db.execute(cls_stmt)).scalar_one_or_none()
        if cid:
            chk_stmt = select(AttendanceSession).where(
                and_(
                    AttendanceSession.class_id == cid,
                    AttendanceSession.session_date == today_date,
                    AttendanceSession.slot_hour == hour_val
                )
            )
            exists = (await db.execute(chk_stmt)).scalar_one_or_none() is not None
            return {"already_submitted": exists, "date": today_str}
    except Exception:
        pass

    exists = sheets.check_attendance_exists(class_id, today_str, hour_val, subject_id)
    return {"already_submitted": exists, "date": today_str}


# ── Faculty Attendance Report ────────────────────────────────────────────────
@router.get("/reports/class/{class_id}")
def get_class_report(
    class_id: str,
    current_user: dict = _faculty_dep,
):
    """Return attendance matrix and student performance stats for the specified class."""
    return sheets.get_class_attendance_report(class_id)
