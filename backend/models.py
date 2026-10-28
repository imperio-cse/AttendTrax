# =============================================================================
# AttendTrax Enterprise – Relational Database Models
# models.py  –  Campus-Wide Multi-Department Schema & Approval Ledgers
# =============================================================================
import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Date, DateTime, 
    ForeignKey, Index, JSON, Float
)
from sqlalchemy.orm import relationship

from database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(20), unique=True, index=True, nullable=False)  # e.g., 'CSE', 'ECE'
    name = Column(String(150), nullable=False)
    hod_user_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="department")
    classes = relationship("ClassRoom", back_populates="department")
    subjects = relationship("Subject", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # Roles: SUPER_ADMIN, DEPT_ADMIN, CLASS_INCHARGE, FACULTY, STUDENT, WARDEN
    role = Column(String(30), index=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=True)
    phone = Column(String(30), nullable=True)
    status = Column(String(20), default="ACTIVE", nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    department = relationship("Department", back_populates="users")
    student_profile = relationship("Student", foreign_keys="Student.user_id", back_populates="user", uselist=False)
    faculty_profile = relationship("Faculty", foreign_keys="Faculty.user_id", back_populates="user", uselist=False)


class ClassRoom(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    class_code = Column(String(50), unique=True, index=True, nullable=False)  # e.g., 'CSE29A'
    class_name = Column(String(150), nullable=False)                          # e.g., 'II CSE A'
    year = Column(Integer, nullable=False, default=1)                         # 1..4
    section = Column(String(10), nullable=False, default="A")
    semester = Column(Integer, nullable=False, default=1)                     # 1..8
    academic_year = Column(String(20), default="2026-2027", nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    department = relationship("Department", back_populates="classes")
    students = relationship("Student", back_populates="class_room")
    sessions = relationship("AttendanceSession", back_populates="class_room")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    reg_no = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    roll_no = Column(String(50), nullable=True)
    # DAY_SCHOLAR vs HOSTELLER
    residence_type = Column(String(20), default="DAY_SCHOLAR", nullable=False)
    class_incharge_faculty_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    warden_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    hostel_block_room = Column(String(50), nullable=True)
    status = Column(String(20), default="ACTIVE", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="student_profile")
    class_room = relationship("ClassRoom", back_populates="students")
    attendance_records = relationship("AttendanceRecord", back_populates="student")
    leave_applications = relationship("StudentLeave", back_populates="student")


class Faculty(Base):
    __tablename__ = "faculty"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    faculty_code = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    designation = Column(String(100), default="Assistant Professor", nullable=False)
    qualification = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="faculty_profile")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subject_code = Column(String(50), index=True, nullable=False)
    subject_name = Column(String(150), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    semester = Column(Integer, default=1, nullable=False)
    subject_type = Column(String(20), default="THEORY", nullable=False) # THEORY, LAB, ELECTIVE
    is_active = Column(Boolean, default=True, nullable=False)

    department = relationship("Department", back_populates="subjects")


class FacultyAllocation(Base):
    __tablename__ = "faculty_allocations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)
    academic_year = Column(String(20), default="2026-2027", nullable=False)
    semester = Column(Integer, default=1, nullable=False)


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True, autoincrement=True)
    session_uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    faculty_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_date = Column(Date, nullable=False, index=True)
    slot_hour = Column(String(20), default="DAY", nullable=False)   # DAY or H1..H8
    session_type = Column(String(20), default="DAILY", nullable=False) # DAILY or HOURLY
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    modified_at = Column(DateTime, nullable=True)
    lock_status = Column(String(20), default="LOCKED", nullable=False) # LOCKED, MODIFIED

    class_room = relationship("ClassRoom", back_populates="sessions")
    records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_session_lookup", "class_id", "session_date", "slot_hour", "subject_id"),
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True, autoincrement=True)
    session_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    status = Column(String(10), nullable=False) # P, A, OD, L
    remarks = Column(String(255), nullable=True)

    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("Student", back_populates="attendance_records")

    __table_args__ = (
        Index("idx_record_student_status", "student_id", "status"),
    )


# ═════════════════════════════════════════════════════════════════════════════
# LEAVE & PERMISSION WORKFLOW ENGINES
# ═════════════════════════════════════════════════════════════════════════════

class FacultyLeave(Base):
    __tablename__ = "faculty_leaves"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    faculty_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    
    # Categories: CASUAL, MEDICAL, ON_DUTY, PERMISSION, EARNED
    leave_category = Column(String(30), default="CASUAL", nullable=False)
    # Scope: FULL_DAY, FN_HALF_DAY, AN_HALF_DAY, SPECIFIC_HOURS
    session_scope = Column(String(30), default="FULL_DAY", nullable=False)
    
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    specific_time_window = Column(String(50), nullable=True) # e.g. "09:00-10:30"
    reason = Column(Text, nullable=False)
    attachment_url = Column(String(255), nullable=True)

    # 2-Tier Approval Flow: HOD -> Principal / VP
    hod_status = Column(String(20), default="PENDING", nullable=False) # PENDING, APPROVED, REJECTED
    hod_remarks = Column(Text, nullable=True)
    hod_action_at = Column(DateTime, nullable=True)
    hod_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    principal_status = Column(String(20), default="PENDING", nullable=False) # PENDING, APPROVED, REJECTED
    principal_remarks = Column(Text, nullable=True)
    principal_action_at = Column(DateTime, nullable=True)
    principal_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Global State: PENDING, HOD_APPROVED, APPROVED, REJECTED
    final_status = Column(String(20), default="PENDING", index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StudentLeave(Base):
    __tablename__ = "student_leaves"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)

    # DAY_SCHOLAR vs HOSTELLER
    residence_type = Column(String(20), nullable=False)
    # ON_DUTY, MEDICAL, CASUAL, GATE_PASS
    leave_type = Column(String(30), default="CASUAL", nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    attachment_url = Column(String(255), nullable=True)

    # Approval Queue:
    # Day Scholar: Class Incharge -> HOD
    # Hosteller: Class Incharge -> HOD -> Hostel Warden
    incharge_status = Column(String(20), default="PENDING", nullable=False)
    incharge_remarks = Column(Text, nullable=True)
    incharge_action_at = Column(DateTime, nullable=True)
    incharge_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    hod_status = Column(String(20), default="PENDING", nullable=False)
    hod_remarks = Column(Text, nullable=True)
    hod_action_at = Column(DateTime, nullable=True)
    hod_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    warden_status = Column(String(20), default="NOT_APPLICABLE", nullable=False)
    warden_remarks = Column(Text, nullable=True)
    warden_action_at = Column(DateTime, nullable=True)
    warden_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # PENDING, INCHARGE_APPROVED, HOD_APPROVED, APPROVED, REJECTED
    final_status = Column(String(25), default="PENDING", index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("Student", back_populates="leave_applications")
    gate_pass = relationship("HostelGatePass", back_populates="leave_application", uselist=False)


class HostelGatePass(Base):
    __tablename__ = "hostel_gate_passes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    leave_id = Column(Integer, ForeignKey("student_leaves.id"), unique=True, nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    pass_token = Column(String(64), unique=True, index=True, nullable=False)
    qr_code_data = Column(Text, nullable=True)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    gate_exit_at = Column(DateTime, nullable=True)
    gate_return_at = Column(DateTime, nullable=True)
    security_officer_name = Column(String(100), nullable=True)
    pass_status = Column(String(20), default="ISSUED", nullable=False) # ISSUED, EXITED, RETURNED, EXPIRED

    leave_application = relationship("StudentLeave", back_populates="gate_pass")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False) # e.g. LOGIN, ATTENDANCE_OVERRIDE, LEAVE_APPROVE
    target_entity = Column(String(50), nullable=False) # e.g. AttendanceSession, FacultyLeave
    target_id = Column(BigInteger, nullable=True)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
