# =============================================================================
# AttendTrax Enterprise – Comprehensive Database Hydrator & Accelerator
# hydrate_db.py – Migrates all Google Sheets data into SQL and seeds 8-Dept Data
# =============================================================================
import asyncio
import os
import re
import sys
from datetime import datetime, date, timedelta

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select, and_, func
from database import init_db, get_session_factory
from models import (
    Department, User, ClassRoom, Student, Faculty, Subject,
    AttendanceSession, AttendanceRecord, FacultyLeave, StudentLeave
)
from auth import hash_password

DEPARTMENTS_DATA = [
    {"code": "CSE",   "name": "Department of Computer Science & Engineering", "hod_name": "Dr. Antony Sudha K (HOD CSE)"},
    {"code": "ECE",   "name": "Department of Electronics & Communication Engineering", "hod_name": "Dr. M. Senthilvelan (HOD ECE)"},
    {"code": "EEE",   "name": "Department of Electrical & Electronics Engineering", "hod_name": "Dr. P. Ramesh (HOD EEE)"},
    {"code": "MECH",  "name": "Department of Mechanical Engineering", "hod_name": "Dr. V. Anand (HOD MECH)"},
    {"code": "CIVIL", "name": "Department of Civil Engineering", "hod_name": "Dr. G. Karthik (HOD CIVIL)"},
    {"code": "IT",    "name": "Department of Information Technology", "hod_name": "Dr. S. Priya (HOD IT)"},
    {"code": "AIDS",  "name": "Department of Artificial Intelligence & Data Science", "hod_name": "Dr. K. Rajesh (HOD AI&DS)"},
    {"code": "CSBS",  "name": "Department of Computer Science & Business Systems", "hod_name": "Dr. N. Balaji (HOD CSBS)"},
]

FACULTY_SEED = [
    {"username": "fathima.cse", "code": "CSE002", "name": "Fathima A", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "antonysudha.cse", "code": "CS001", "name": "Dr ANTONY SUDHA K", "dept": "CSE", "desig": "Professor & Head"},
    {"username": "manickam.cse", "code": "CSE003", "name": "Manickam R", "dept": "CSE", "desig": "Associate Professor"},
    {"username": "dhanalakshmi.cse", "code": "CSE004", "name": "Dhanalakshmi", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "aishwarya.cse", "code": "CSE005", "name": "Aishwarya", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "jothika.cse", "code": "CSE006", "name": "Jothika", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "jeevitha.cse", "code": "CSE007", "name": "Jeevitha", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "sasipriya.cse", "code": "CSE008", "name": "Sasipriya", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "yuvaraj.cse", "code": "CSE009", "name": "Yuvaraj", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "nithya.cse", "code": "CSE010", "name": "Nithya", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "suresh.cse", "code": "CSE011", "name": "Suresh", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "kg.cse", "code": "CSE000", "name": "Mr KG", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "pradeesh.cse", "code": "CS111", "name": "Pradeeshwar", "dept": "CSE", "desig": "Assistant Professor"},
    {"username": "nare.cse", "code": "CSE616", "name": "Narendhar DS", "dept": "CSE", "desig": "Assistant Professor"},
    # Other Department Faculty Members
    {"username": "senthil.ece", "code": "ECE001", "name": "Dr. M. Senthilvelan", "dept": "ECE", "desig": "Professor & Head"},
    {"username": "ramesh.eee", "code": "EEE001", "name": "Dr. P. Ramesh", "dept": "EEE", "desig": "Professor & Head"},
    {"username": "anand.mech", "code": "MECH001", "name": "Dr. V. Anand", "dept": "MECH", "desig": "Professor & Head"},
    {"username": "karthik.civil", "code": "CIV001", "name": "Dr. G. Karthik", "dept": "CIVIL", "desig": "Professor & Head"},
    {"username": "priya.it", "code": "IT001", "name": "Dr. S. Priya", "dept": "IT", "desig": "Professor & Head"},
    {"username": "rajesh.aids", "code": "AIDS001", "name": "Dr. K. Rajesh", "dept": "AIDS", "desig": "Professor & Head"},
    {"username": "balaji.csbs", "code": "CSBS001", "name": "Dr. N. Balaji", "dept": "CSBS", "desig": "Professor & Head"},
]

CLASSES_SEED = [
    # CSE
    {"code": "CSE29A", "name": "CSE II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "CSE"},
    {"code": "CSE29B", "name": "CSE II Year B", "year": 2, "sec": "B", "sem": 3, "dept": "CSE"},
    {"code": "CSE28A", "name": "CSE III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "CSE"},
    {"code": "CSE28B", "name": "CSE III Year B", "year": 3, "sec": "B", "sem": 5, "dept": "CSE"},
    {"code": "CSE27A", "name": "CSE IV Year A", "year": 4, "sec": "A", "sem": 7, "dept": "CSE"},
    # ECE
    {"code": "ECE29A", "name": "ECE II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "ECE"},
    {"code": "ECE28A", "name": "ECE III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "ECE"},
    {"code": "ECE27A", "name": "ECE IV Year A", "year": 4, "sec": "A", "sem": 7, "dept": "ECE"},
    # EEE
    {"code": "EEE29A", "name": "EEE II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "EEE"},
    {"code": "EEE28A", "name": "EEE III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "EEE"},
    # MECH
    {"code": "MECH29A", "name": "MECH II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "MECH"},
    {"code": "MECH28A", "name": "MECH III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "MECH"},
    # CIVIL
    {"code": "CIVIL29A", "name": "CIVIL II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "CIVIL"},
    {"code": "CIVIL28A", "name": "CIVIL III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "CIVIL"},
    # IT
    {"code": "IT29A", "name": "IT II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "IT"},
    {"code": "IT28A", "name": "IT III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "IT"},
    # AIDS
    {"code": "AIDS29A", "name": "AI&DS II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "AIDS"},
    {"code": "AIDS28A", "name": "AI&DS III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "AIDS"},
    # CSBS
    {"code": "CSBS29A", "name": "CSBS II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "CSBS"},
    {"code": "CSBS28A", "name": "CSBS III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "CSBS"},
]


async def hydrate():
    print("=== [ATTENDTRAX ACCELERATOR] Starting Database Hydration ===")
    await init_db()
    session_factory = get_session_factory()

    async with session_factory() as session:
        # 1. Departments
        dept_id_map = {}
        for d in DEPARTMENTS_DATA:
            stmt = select(Department).where(Department.code == d["code"])
            res = await session.execute(stmt)
            dept = res.scalar_one_or_none()
            if not dept:
                dept = Department(code=d["code"], name=d["name"], is_active=True)
                session.add(dept)
                await session.flush()
                print(f"  + Department added: {d['code']}")
            dept_id_map[d["code"]] = dept.id

        # 2. Super Admins
        super_admins = [
            ("principal", "Dr. R. Shanmugasundaram (Principal)", "Principal@2026"),
            ("viceprincipal", "Dr. K. Senthil Kumar (Vice Principal)", "VP@2026"),
            ("admin", "Central System Administrator", "AttendTrax@2026"),
        ]
        for uname, fname, pwd in super_admins:
            stmt = select(User).where(User.username == uname)
            res = await session.execute(stmt)
            u = res.scalar_one_or_none()
            if not u:
                u = User(
                    username=uname,
                    full_name=fname,
                    password_hash=hash_password(pwd),
                    role="SUPER_ADMIN",
                    status="ACTIVE"
                )
                session.add(u)
                await session.flush()
                print(f"  + Super Admin added: {uname}")
            else:
                # Ensure password hash is valid
                u.password_hash = hash_password(pwd)

        # 3. Department HODs
        for d in DEPARTMENTS_DATA:
            code = d["code"]
            dept_id = dept_id_map[code]
            hod_uname = f"hod.{code.lower()}"
            stmt = select(User).where(User.username == hod_uname)
            res = await session.execute(stmt)
            hod_u = res.scalar_one_or_none()
            if not hod_u:
                hod_u = User(
                    username=hod_uname,
                    full_name=d["hod_name"],
                    password_hash=hash_password("Hod@2026"),
                    role="DEPT_ADMIN",
                    department_id=dept_id,
                    status="ACTIVE"
                )
                session.add(hod_u)
                await session.flush()
                print(f"  + HOD added: {hod_uname}")
            else:
                hod_u.password_hash = hash_password("Hod@2026")
                hod_u.full_name = d["hod_name"]

            # Link to Department
            d_obj = await session.get(Department, dept_id)
            if d_obj:
                d_obj.hod_user_id = hod_u.id

        # 4. Hostel Wardens
        wardens = [
            ("warden.boys", "Chief Warden (Boys Hostel)", "Warden@2026"),
            ("warden.girls", "Chief Warden (Girls Hostel)", "Warden@2026"),
        ]
        for w_uname, w_name, w_pwd in wardens:
            stmt = select(User).where(User.username == w_uname)
            res = await session.execute(stmt)
            w_u = res.scalar_one_or_none()
            if not w_u:
                w_u = User(
                    username=w_uname,
                    full_name=w_name,
                    password_hash=hash_password(w_pwd),
                    role="WARDEN",
                    status="ACTIVE"
                )
                session.add(w_u)
                await session.flush()
                print(f"  + Warden added: {w_uname}")
            else:
                w_u.password_hash = hash_password(w_pwd)

        # 5. Classes across 8 departments
        class_id_map = {}
        for c in CLASSES_SEED:
            dept_id = dept_id_map.get(c["dept"])
            stmt = select(ClassRoom).where(ClassRoom.class_code == c["code"])
            res = await session.execute(stmt)
            cls_obj = res.scalar_one_or_none()
            if not cls_obj:
                cls_obj = ClassRoom(
                    department_id=dept_id,
                    class_code=c["code"],
                    class_name=c["name"],
                    year=c["year"],
                    section=c["sec"],
                    semester=c["sem"],
                    academic_year="2026-2027",
                    status="ACTIVE"
                )
                session.add(cls_obj)
                await session.flush()
                print(f"  + Class added: {c['code']} ({c['name']})")
            class_id_map[c["code"]] = cls_obj.id

        # 6. Faculty Members (Sync Google Sheets faculty + standardized password Staff@2026)
        user_id_map = {}
        faculty_id_map = {}
        for f in FACULTY_SEED:
            dept_id = dept_id_map.get(f["dept"], dept_id_map["CSE"])
            stmt = select(User).where(User.username == f["username"])
            res = await session.execute(stmt)
            u = res.scalar_one_or_none()
            if not u:
                u = User(
                    username=f["username"],
                    full_name=f["name"],
                    password_hash=hash_password("Staff@2026"),
                    role="FACULTY",
                    department_id=dept_id,
                    status="ACTIVE"
                )
                session.add(u)
                await session.flush()
                print(f"  + Faculty User added: {f['username']} ({f['name']})")
            else:
                u.password_hash = hash_password("Staff@2026")
                u.full_name = f["name"]
                u.department_id = dept_id

            user_id_map[f["username"]] = u.id

            # Add to Faculty profile table
            f_stmt = select(Faculty).where(Faculty.faculty_code == f["code"])
            f_res = await session.execute(f_stmt)
            fac_obj = f_res.scalar_one_or_none()
            if not fac_obj:
                fac_obj = Faculty(
                    faculty_code=f["code"],
                    user_id=u.id,
                    department_id=dept_id,
                    designation=f["desig"]
                )
                session.add(fac_obj)
                await session.flush()
            faculty_id_map[f["code"]] = fac_obj.id

        # 7. Students (Migrate from Sheets + Ensure Students exist across classes)
        student_reg_map = {}
        try:
            import sheets
            raw_students = sheets.get_all_students()
            print(f"  -> Found {len(raw_students)} student records in Google Sheets. Syncing into SQL...")
            for s in raw_students:
                rn = str(s.get("RegNo", "")).strip()
                if not rn:
                    continue
                s_name = str(s.get("Name", "")).strip()
                cid_str = str(s.get("ClassID", "")).strip()
                cid = class_id_map.get(cid_str) or class_id_map.get("CSE29A")
                dept_id = dept_id_map["CSE"]

                # Check student user
                u_stmt = select(User).where(User.username == rn)
                u_res = await session.execute(u_stmt)
                s_u = u_res.scalar_one_or_none()
                if not s_u:
                    s_u = User(
                        username=rn,
                        full_name=s_name,
                        password_hash=hash_password(f"{rn}@CSE"),
                        role="STUDENT",
                        department_id=dept_id,
                        status="ACTIVE"
                    )
                    session.add(s_u)
                    await session.flush()

                # Student profile
                st_stmt = select(Student).where(Student.reg_no == rn)
                st_res = await session.execute(st_stmt)
                st_obj = st_res.scalar_one_or_none()
                if not st_obj:
                    st_obj = Student(
                        reg_no=rn,
                        user_id=s_u.id,
                        class_id=cid,
                        department_id=dept_id,
                        name=s_name,
                        residence_type="DAY_SCHOLAR" if (int(rn[-2:]) % 3 != 0) else "HOSTELLER",
                        status="ACTIVE"
                    )
                    session.add(st_obj)
                    await session.flush()
                student_reg_map[rn] = st_obj.id
        except Exception as e:
            print(f"  [Warning] Student sync from sheets error: {e}")

        # Ensure other classes have student cohorts so 8-dept statistics are populated
        demo_depts = [
            ("ECE", "ECE29A", "410125106"),
            ("EEE", "EEE29A", "410125105"),
            ("MECH", "MECH29A", "410125114"),
            ("CIVIL", "CIVIL29A", "410125103"),
            ("IT", "IT29A", "410125205"),
            ("AIDS", "AIDS29A", "410125243"),
            ("CSBS", "CSBS29A", "410125244"),
        ]
        sample_names = ["Aarav", "Bhavna", "Chirag", "Divya", "Eashwar", "Farhan", "Gayathri", "Harish", "Ishaan", "Jayashree", "Karthik", "Lakshmi", "Manish", "Nithya", "Omkar", "Pooja", "Rahul", "Swathi", "Tarun", "Varsha"]

        for d_code, c_code, prefix in demo_depts:
            dept_id = dept_id_map[d_code]
            cls_id = class_id_map[c_code]
            for i, nm in enumerate(sample_names, start=1):
                rn = f"{prefix}{i:03d}"
                st_stmt = select(Student).where(Student.reg_no == rn)
                res = await session.execute(st_stmt)
                if not res.scalar_one_or_none():
                    u = User(
                        username=rn,
                        full_name=f"{nm} ({d_code})",
                        password_hash=hash_password(f"{rn}@{d_code}"),
                        role="STUDENT",
                        department_id=dept_id,
                        status="ACTIVE"
                    )
                    session.add(u)
                    await session.flush()

                    st = Student(
                        reg_no=rn,
                        user_id=u.id,
                        class_id=cls_id,
                        department_id=dept_id,
                        name=f"{nm} ({d_code})",
                        residence_type="DAY_SCHOLAR" if i % 2 == 0 else "HOSTELLER",
                        status="ACTIVE"
                    )
                    session.add(st)
                    await session.flush()
                    student_reg_map[rn] = st.id

        await session.commit()
        print(f"  + Total indexed students in SQL: {len(student_reg_map)}")

        # 8. Migrate Attendance Records from Google Sheets into SQL
        try:
            import sheets
            raw_logs = sheets._get_raw_attendance_log()
            print(f"  -> Migrating {len(raw_logs)} attendance logs from Google Sheets into SQL...")

            # Group logs by (ClassID, Date, Hour)
            sessions_dict = {}
            for row in raw_logs:
                d_str = str(row.get("Date", "")).strip()
                cid_str = str(row.get("ClassID", "")).strip()
                hr_str = str(row.get("Hour", "DAILY")).strip().upper()
                rn_str = str(row.get("RegNo", "")).strip()
                status_val = str(row.get("Status", "P")).strip().upper() or "P"

                if not d_str or not cid_str or not rn_str:
                    continue

                # Parse date
                try:
                    s_date = datetime.strptime(d_str, "%d-%m-%Y").date()
                except Exception:
                    try:
                        s_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                    except Exception:
                        continue

                cid = class_id_map.get(cid_str) or class_id_map.get("CSE29A")
                key = (cid, s_date, hr_str)
                if key not in sessions_dict:
                    sessions_dict[key] = []
                sessions_dict[key].append((rn_str, status_val))

            inserted_sessions = 0
            inserted_records = 0

            # Find a faculty user ID for fallback
            f_user_stmt = select(User.id).where(User.role == "FACULTY").limit(1)
            f_uid = (await session.execute(f_user_stmt)).scalar_one_or_none() or 1

            for (cid, s_date, hr_str), recs in sessions_dict.items():
                # Check if session exists
                sess_stmt = select(AttendanceSession).where(
                    and_(
                        AttendanceSession.class_id == cid,
                        AttendanceSession.session_date == s_date,
                        AttendanceSession.slot_hour == hr_str
                    )
                )
                sess = (await session.execute(sess_stmt)).scalar_one_or_none()
                if not sess:
                    sess = AttendanceSession(
                        class_id=cid,
                        session_date=s_date,
                        slot_hour=hr_str,
                        session_type="DAILY" if hr_str in ("DAILY", "DAY") else "HOURLY",
                        faculty_id=f_uid,
                        lock_status="LOCKED"
                    )
                    session.add(sess)
                    await session.flush()
                    inserted_sessions += 1

                for rn_str, st_val in recs:
                    st_id = student_reg_map.get(rn_str)
                    if not st_id:
                        continue
                    # Check record
                    r_stmt = select(AttendanceRecord).where(
                        and_(AttendanceRecord.session_id == sess.id, AttendanceRecord.student_id == st_id)
                    )
                    existing_r = (await session.execute(r_stmt)).scalar_one_or_none()
                    if not existing_r:
                        rec_obj = AttendanceRecord(
                            session_id=sess.id,
                            student_id=st_id,
                            status=st_val
                        )
                        session.add(rec_obj)
                        inserted_records += 1

            await session.commit()
            print(f"  + Migrated {inserted_sessions} sessions and {inserted_records} attendance records into SQL!")
        except Exception as ex:
            await session.rollback()
            print(f"  [Warning] Sheets attendance log migration notice: {ex}")

        # 9. Generate realistic baseline attendance for other departments across past 25 days & today
        print("  -> Generating realistic attendance sessions for all 8 departments...")
        today = date.today()
        working_dates = []
        cur_d = today
        while len(working_dates) < 25:
            if cur_d.weekday() < 5: # Mon-Fri
                working_dates.append(cur_d)
            cur_d -= timedelta(days=1)
        working_dates.reverse()

        # Target departmental rates:
        dept_rates = {
            "CSE": 0.912,
            "AIDS": 0.885,
            "ECE": 0.871,
            "IT": 0.864,
            "MECH": 0.840,
            "CIVIL": 0.823,
            "EEE": 0.801,
            "CSBS": 0.794,
        }

        import random
        random.seed(42)

        for d_code, c_code, _ in demo_depts:
            cls_id = class_id_map.get(c_code)
            if not cls_id:
                continue

            target_rate = dept_rates.get(d_code, 0.85)

            # Get students in this class
            st_stmt = select(Student).where(Student.class_id == cls_id)
            cls_students = (await session.execute(st_stmt)).scalars().all()
            if not cls_students:
                continue

            f_uid = user_id_map.get(f"{d_code.lower()}001") or 1

            for s_date in working_dates:
                # For today, make some classes submitted and some pending
                if s_date == today and d_code in ("MECH", "CSBS"):
                    continue # leave pending today for live radar demonstration!

                # Check if session exists
                sess_stmt = select(AttendanceSession).where(
                    and_(
                        AttendanceSession.class_id == cls_id,
                        AttendanceSession.session_date == s_date,
                        AttendanceSession.slot_hour == "DAY"
                    )
                )
                sess = (await session.execute(sess_stmt)).scalar_one_or_none()
                if not sess:
                    sess = AttendanceSession(
                        class_id=cls_id,
                        session_date=s_date,
                        slot_hour="DAY",
                        session_type="DAILY",
                        faculty_id=f_uid,
                        lock_status="LOCKED"
                    )
                    session.add(sess)
                    await session.flush()

                for idx, st_obj in enumerate(cls_students):
                    # Deterministic absentee assignment to create predictable defaulters
                    # e.g., students 1 and 2 miss more days to become critical defaulters (<65%)
                    if idx in (0, 1):
                        is_present = random.random() < 0.58 # critical defaulter
                    elif idx in (2, 3):
                        is_present = random.random() < 0.71 # warning defaulter (65-75%)
                    else:
                        is_present = random.random() < target_rate

                    status_str = "P" if is_present else ("OD" if random.random() < 0.1 else "A")

                    r_stmt = select(AttendanceRecord).where(
                        and_(AttendanceRecord.session_id == sess.id, AttendanceRecord.student_id == st_obj.id)
                    )
                    if not (await session.execute(r_stmt)).scalar_one_or_none():
                        session.add(AttendanceRecord(
                            session_id=sess.id,
                            student_id=st_obj.id,
                            status=status_str
                        ))

        await session.commit()
        print("  + 8-Department baseline attendance generated successfully.")

        # 10. Seed Realistic Faculty Leaves for Principal Level-2 Sign-off
        print("  -> Seeding pending faculty leaves for Principal Level-2 queue...")
        pending_leaves = [
            {
                "faculty_uname": "fathima.cse",
                "dept": "CSE",
                "cat": "CASUAL",
                "scope": "FN_HALF_DAY",
                "start": today + timedelta(days=1),
                "end": today + timedelta(days=1),
                "reason": "Attending Anna University Doctoral Committee Research Meeting as External Reviewer.",
                "hod_remarks": "Recommended. Class adjustment arranged with Prof. Manickam R.",
            },
            {
                "faculty_uname": "manickam.cse",
                "dept": "CSE",
                "cat": "MEDICAL",
                "scope": "FULL_DAY",
                "start": today + timedelta(days=2),
                "end": today + timedelta(days=2),
                "reason": "Dental surgery and post-operative medical consultation.",
                "hod_remarks": "Medical certificate verified. Recommended.",
            },
            {
                "faculty_uname": "senthil.ece",
                "dept": "ECE",
                "cat": "ON_DUTY",
                "scope": "SPECIFIC_HOURS",
                "start": today + timedelta(days=3),
                "end": today + timedelta(days=3),
                "time": "09:30 AM - 12:30 PM",
                "reason": "Keynote Speaker presentation at IEEE International Smart Systems Conference.",
                "hod_remarks": "Approved and forwarded for executive sanction.",
            },
            {
                "faculty_uname": "priya.it",
                "dept": "IT",
                "cat": "CASUAL",
                "scope": "FULL_DAY",
                "start": today + timedelta(days=4),
                "end": today + timedelta(days=4),
                "reason": "Family function and travel to home town.",
                "hod_remarks": "Substitute faculty allotted for III-IT theory period.",
            }
        ]

        for pl in pending_leaves:
            f_uid = user_id_map.get(pl["faculty_uname"]) or 1
            d_id = dept_id_map.get(pl["dept"])
            stmt = select(FacultyLeave).where(
                and_(
                    FacultyLeave.faculty_id == f_uid,
                    FacultyLeave.start_date == pl["start"],
                    FacultyLeave.reason == pl["reason"]
                )
            )
            if not (await session.execute(stmt)).scalar_one_or_none():
                leave = FacultyLeave(
                    faculty_id=f_uid,
                    department_id=d_id,
                    leave_category=pl["cat"],
                    session_scope=pl["scope"],
                    start_date=pl["start"],
                    end_date=pl["end"],
                    specific_time_window=pl.get("time"),
                    reason=pl["reason"],
                    hod_status="APPROVED",
                    hod_remarks=pl["hod_remarks"],
                    hod_action_at=datetime.utcnow() - timedelta(hours=2),
                    hod_user_id=1,
                    principal_status="PENDING",
                    final_status="HOD_APPROVED",
                )
                session.add(leave)
                print(f"  + Added Pending Leave for Principal Queue: {pl['faculty_uname']} ({pl['scope']})")

        await session.commit()
        print("\n=== [HYDRATION COMPLETE] AttendTrax Enterprise Database is fully populated & optimized! ===")


async def ensure_hydrated():
    """Checks if the database has been populated with core roles (e.g. principal).
    If missing or empty, runs hydration automatically."""
    try:
        await init_db()
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(func.count(User.id))
            user_count = (await session.execute(stmt)).scalar() or 0
            stmt_princ = select(User).where(User.username == "principal")
            princ = (await session.execute(stmt_princ)).scalar_one_or_none()
            if user_count < 10 or not princ:
                print(f"[AUTO-HYDRATION] Database contains {user_count} users. Seeding all departments, users, and telemetry...")
                await hydrate()
            else:
                print(f"[AUTO-HYDRATION] Database healthy with {user_count} users. Skipping hydration.")
    except Exception as e:
        print(f"[AUTO-HYDRATION ERROR] Failed to verify/hydrate database: {e}")


if __name__ == "__main__":
    asyncio.run(hydrate())

