# =============================================================================
# routers/faculty_router.py  –  Faculty endpoints
# =============================================================================
from datetime import date
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import sheets
from dependencies import require_role
from sheets import ALL_HOURS, HOUR_LABELS

router = APIRouter(prefix="/faculty", tags=["Faculty"])

_faculty_dep = Depends(require_role("FACULTY", "ADMIN"))


# ── GET helpers ───────────────────────────────────────────────────────────────
@router.get("/classes")
def list_classes(current_user: dict = _faculty_dep):
    """Return all active classes (faculty needs to select one)."""
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
def list_students(class_id: str, _=_faculty_dep):
    """Return students for attendance marking."""
    return sheets.get_students_for_attendance(class_id)


# ── Attendance submission ─────────────────────────────────────────────────────
class AttendanceEntry(BaseModel):
    reg_no: str
    status: str   # "P", "A", or "OD"


class SubmitAttendanceRequest(BaseModel):
    class_id: str
    subject_id: str
    hour: str = "DAY"   # Defaults to single daily attendance "DAY"
    attendance: List[AttendanceEntry]


@router.post("/attendance")
def submit_attendance(
    body: SubmitAttendanceRequest,
    current_user: dict = _faculty_dep,
):
    hour_val = (body.hour or "DAY").strip().upper()

    # Validate status values: "P" (Present), "A" (Absent), "OD" (On-Duty)
    for entry in body.attendance:
        st = entry.status.upper()
        if st not in ("P", "A", "OD", "-"):
            raise HTTPException(status_code=400, detail=f"Invalid status '{entry.status}'. Use P, A, or OD.")

    # Auto fetch today's date (IST)
    today_str = sheets.get_ist_today_str()

    # ── Immutability check (backend-enforced) ────────────────────────────
    if sheets.check_attendance_exists(body.class_id, today_str, hour_val, body.subject_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Attendance for {body.class_id} / {body.subject_id} "
                f"on {today_str} has already been submitted today and cannot be modified."
            ),
        )

    faculty_id = str(current_user.get("UserID", ""))
    attendance_map: Dict[str, str] = {e.reg_no: e.status.upper() for e in body.attendance}

    sheets.save_attendance(
        class_id=body.class_id,
        date_str=today_str,
        hour=hour_val,
        subject_id=body.subject_id,
        faculty_id=faculty_id,
        attendance=attendance_map,
    )
    return {"message": "Attendance saved successfully.", "date": today_str}


# ── Check if slot already submitted ──────────────────────────────────────────
@router.get("/attendance/check")
def check_slot(
    class_id: str,
    subject_id: str = "",
    hour: str = "DAY",
    _=_faculty_dep,
):
    today_str = sheets.get_ist_today_str()
    hour_val = (hour or "DAY").strip().upper()
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


