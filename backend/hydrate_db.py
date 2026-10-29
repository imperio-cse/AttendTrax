# =============================================================================
# AttendTrax Enterprise – High-Speed Supabase & PostgreSQL Hydrator
# hydrate_db.py – Batch-optimized for Cloud & Local execution (<5 seconds)
# =============================================================================
import asyncio
import os
import random
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
    {"username": "senthil.ece", "code": "ECE001", "name": "Dr. M. Senthilvelan", "dept": "ECE", "desig": "Professor & Head"},
    {"username": "ramesh.eee", "code": "EEE001", "name": "Dr. P. Ramesh", "dept": "EEE", "desig": "Professor & Head"},
    {"username": "anand.mech", "code": "MECH001", "name": "Dr. V. Anand", "dept": "MECH", "desig": "Professor & Head"},
    {"username": "karthik.civil", "code": "CIV001", "name": "Dr. G. Karthik", "dept": "CIVIL", "desig": "Professor & Head"},
    {"username": "priya.it", "code": "IT001", "name": "Dr. S. Priya", "dept": "IT", "desig": "Professor & Head"},
    {"username": "rajesh.aids", "code": "AIDS001", "name": "Dr. K. Rajesh", "dept": "AIDS", "desig": "Professor & Head"},
    {"username": "balaji.csbs", "code": "CSBS001", "name": "Dr. N. Balaji", "dept": "CSBS", "desig": "Professor & Head"},
]

CLASSES_SEED = [
    {"code": "CSE29A", "name": "CSE II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "CSE"},
    {"code": "CSE29B", "name": "CSE II Year B", "year": 2, "sec": "B", "sem": 3, "dept": "CSE"},
    {"code": "CSE28A", "name": "CSE III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "CSE"},
    {"code": "CSE28B", "name": "CSE III Year B", "year": 3, "sec": "B", "sem": 5, "dept": "CSE"},
    {"code": "CSE27A", "name": "CSE IV Year A", "year": 4, "sec": "A", "sem": 7, "dept": "CSE"},
    {"code": "ECE29A", "name": "ECE II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "ECE"},
    {"code": "ECE28A", "name": "ECE III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "ECE"},
    {"code": "ECE27A", "name": "ECE IV Year A", "year": 4, "sec": "A", "sem": 7, "dept": "ECE"},
    {"code": "EEE29A", "name": "EEE II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "EEE"},
    {"code": "EEE28A", "name": "EEE III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "EEE"},
    {"code": "MECH29A", "name": "MECH II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "MECH"},
    {"code": "MECH28A", "name": "MECH III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "MECH"},
    {"code": "CIVIL29A", "name": "CIVIL II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "CIVIL"},
    {"code": "CIVIL28A", "name": "CIVIL III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "CIVIL"},
    {"code": "IT29A", "name": "IT II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "IT"},
    {"code": "IT28A", "name": "IT III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "IT"},
    {"code": "AIDS29A", "name": "AI&DS II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "AIDS"},
    {"code": "AIDS28A", "name": "AI&DS III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "AIDS"},
    {"code": "CSBS29A", "name": "CSBS II Year A", "year": 2, "sec": "A", "sem": 3, "dept": "CSBS"},
    {"code": "CSBS28A", "name": "CSBS III Year A", "year": 3, "sec": "A", "sem": 5, "dept": "CSBS"},
]


async def hydrate():
    print("=== [ATTENDTRAX ACCELERATOR] Starting High-Speed Database Hydration ===")
    await init_db()

    # Pre-compute shared hashes once to prevent CPU bottleneck
    print("[1/6] Pre-computing role password hashes...")
    hashes = {
        "principal": hash_password("Principal@2026"),
        "vp": hash_password("VP@2026"),
        "admin": hash_password("AttendTrax@2026"),
        "hod": hash_password("Hod@2026"),
        "warden": hash_password("Warden@2026"),
        "faculty": hash_password("Staff@2026"),
        "student": hash_password("Student@2026"),
    }

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. Departments
        print("[2/6] Hydrating 8 Academic Departments...")
        dept_id_map = {}
        for d in DEPARTMENTS_DATA:
            stmt = select(Department).where(Department.code == d["code"])
            res = await session.execute(stmt)
            dept = res.scalar_one_or_none()
            if not dept:
                dept = Department(code=d["code"], name=d["name"], is_active=True)
                session.add(dept)
                await session.flush()
            dept_id_map[d["code"]] = dept.id
        await session.commit()

        # 2. Institutional Super Admins
        print("[3/6] Seeding Principal, Vice Principal & Central Admin...")
        super_admins = [
            ("principal", "Dr. R. Shanmugasundaram (Principal)", hashes["principal"]),
            ("viceprincipal", "Dr. K. Senthil Kumar (Vice Principal)", hashes["vp"]),
            ("admin", "Central System Administrator", hashes["admin"]),
        ]
        for uname, fname, pwd_h in super_admins:
            stmt = select(User).where(User.username == uname)
            u = (await session.execute(stmt)).scalar_one_or_none()
            if not u:
                session.add(User(username=uname, full_name=fname, password_hash=pwd_h, role="SUPER_ADMIN", status="ACTIVE"))
            else:
                u.password_hash = pwd_h

        # 3. Department HODs & Wardens
        for d in DEPARTMENTS_DATA:
            code = d["code"]
            dept_id = dept_id_map[code]
            hod_uname = f"hod.{code.lower()}"
            stmt = select(User).where(User.username == hod_uname)
            hod_u = (await session.execute(stmt)).scalar_one_or_none()
            if not hod_u:
                hod_u = User(
                    username=hod_uname,
                    full_name=d["hod_name"],
                    password_hash=hashes["hod"],
                    role="DEPT_ADMIN",
                    department_id=dept_id,
                    status="ACTIVE"
                )
                session.add(hod_u)
                await session.flush()
            else:
                hod_u.password_hash = hashes["hod"]

            d_obj = await session.get(Department, dept_id)
            if d_obj:
                d_obj.hod_user_id = hod_u.id

        wardens = [
            ("warden.boys", "Chief Warden (Boys Hostel)", hashes["warden"]),
            ("warden.girls", "Chief Warden (Girls Hostel)", hashes["warden"]),
        ]
        for w_uname, w_name, w_pwd_h in wardens:
            stmt = select(User).where(User.username == w_uname)
            w_u = (await session.execute(stmt)).scalar_one_or_none()
            if not w_u:
                session.add(User(username=w_uname, full_name=w_name, password_hash=w_pwd_h, role="WARDEN", status="ACTIVE"))
            else:
                w_u.password_hash = w_pwd_h

        # 4. Classes across 8 departments
        class_id_map = {}
        for c in CLASSES_SEED:
            dept_id = dept_id_map.get(c["dept"])
            stmt = select(ClassRoom).where(ClassRoom.class_code == c["code"])
            cls_obj = (await session.execute(stmt)).scalar_one_or_none()
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
            class_id_map[c["code"]] = cls_obj.id

        await session.commit()

        # 5. Faculty Members
        print("[4/6] Seeding 50+ Institutional Faculty Profiles...")
        user_id_map = {}
        faculty_id_map = {}
        for f in FACULTY_SEED:
            dept_id = dept_id_map.get(f["dept"], dept_id_map["CSE"])
            stmt = select(User).where(User.username == f["username"])
            u = (await session.execute(stmt)).scalar_one_or_none()
            if not u:
                u = User(
                    username=f["username"],
                    full_name=f["name"],
                    password_hash=hashes["faculty"],
                    role="FACULTY",
                    department_id=dept_id,
                    status="ACTIVE"
                )
                session.add(u)
                await session.flush()
            else:
                u.password_hash = hashes["faculty"]
                u.department_id = dept_id

            user_id_map[f["username"]] = u.id

            f_stmt = select(Faculty).where(Faculty.faculty_code == f["code"])
            fac_obj = (await session.execute(f_stmt)).scalar_one_or_none()
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

        await session.commit()

        # 6. Students across 8 Departments
        print("[5/6] Seeding Student cohorts for all 8 departments...")
        student_reg_map = {}

        # First load existing students from Google Sheets
        try:
            import sheets
            raw_students = sheets.get_all_students()
            for s in raw_students:
                rn = str(s.get("RegNo", "")).strip()
                if not rn:
                    continue
                s_name = str(s.get("Name", "")).strip()
                cid_str = str(s.get("ClassID", "")).strip()
                cid = class_id_map.get(cid_str) or class_id_map.get("CSE29A")
                dept_id = dept_id_map["CSE"]

                stmt = select(User).where(User.username == rn)
                s_u = (await session.execute(stmt)).scalar_one_or_none()
                if not s_u:
                    s_u = User(
                        username=rn,
                        full_name=s_name,
                        password_hash=hashes["student"],
                        role="STUDENT",
                        department_id=dept_id,
                        status="ACTIVE"
                    )
                    session.add(s_u)
                    await session.flush()

                st_stmt = select(Student).where(Student.reg_no == rn)
                st_obj = (await session.execute(st_stmt)).scalar_one_or_none()
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
            print(f"  [Notice] Google Sheets student sync: {e}")

        # Ensure demo cohorts exist for ECE, EEE, MECH, CIVIL, IT, AI&DS, CSBS
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
                st_obj = res.scalar_one_or_none()
                if not st_obj:
                    u = User(
                        username=rn,
                        full_name=f"{nm} ({d_code})",
                        password_hash=hashes["student"],
                        role="STUDENT",
                        department_id=dept_id,
                        status="ACTIVE"
                    )
                    session.add(u)
                    await session.flush()

                    st_obj = Student(
                        reg_no=rn,
                        user_id=u.id,
                        class_id=cls_id,
                        department_id=dept_id,
                        name=f"{nm} ({d_code})",
                        residence_type="DAY_SCHOLAR" if i % 2 == 0 else "HOSTELLER",
                        status="ACTIVE"
                    )
                    session.add(st_obj)
                    await session.flush()
                student_reg_map[rn] = st_obj.id

        await session.commit()
        print(f"  + Students registered: {len(student_reg_map)}")

        # 7. Generate High-Speed Baseline Attendance for 8 Departments
        print("[6/6] Generating 8-Department comparative attendance baseline & leaves...")
        today = date.today()
        working_dates = []
        cur_d = today
        while len(working_dates) < 15:
            if cur_d.weekday() < 5:
                working_dates.append(cur_d)
            cur_d -= timedelta(days=1)
        working_dates.reverse()

        dept_rates = {
            "CSE": 0.92, "AIDS": 0.89, "ECE": 0.87, "IT": 0.86,
            "MECH": 0.84, "CIVIL": 0.82, "EEE": 0.80, "CSBS": 0.79
        }

        random.seed(42)
        for d_code, c_code, _ in demo_depts:
            cls_id = class_id_map.get(c_code)
            if not cls_id:
                continue

            target_rate = dept_rates.get(d_code, 0.85)
            st_stmt = select(Student).where(Student.class_id == cls_id)
            cls_students = (await session.execute(st_stmt)).scalars().all()
            if not cls_students:
                continue

            f_uid = user_id_map.get(f"{d_code.lower()}001") or 1

            # Fetch existing session dates for this class
            existing_dates_stmt = select(AttendanceSession.session_date).where(AttendanceSession.class_id == cls_id)
            existing_dates = set((await session.execute(existing_dates_stmt)).scalars().all())

            for s_date in working_dates:
                if s_date in existing_dates:
                    continue
                if s_date == today and d_code in ("MECH", "CSBS"):
                    continue # leave pending today for live demonstration

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

                records_batch = []
                for idx, st_obj in enumerate(cls_students):
                    if idx in (0, 1):
                        is_present = random.random() < 0.58
                    elif idx in (2, 3):
                        is_present = random.random() < 0.71
                    else:
                        is_present = random.random() < target_rate

                    status_str = "P" if is_present else ("OD" if random.random() < 0.1 else "A")
                    records_batch.append(AttendanceRecord(
                        session_id=sess.id,
                        student_id=st_obj.id,
                        status=status_str
                    ))
                session.add_all(records_batch)

            await session.commit()

        # Seed Pending Faculty Leaves for Principal Queue
        pending_leaves = [
            {
                "faculty_uname": "fathima.cse", "dept": "CSE", "cat": "CASUAL",
                "scope": "FN_HALF_DAY", "start": today + timedelta(days=1), "end": today + timedelta(days=1),
                "reason": "Attending Anna University Doctoral Committee Research Meeting as External Reviewer.",
                "hod_remarks": "Recommended. Class adjustment arranged with Prof. Manickam R."
            },
            {
                "faculty_uname": "senthil.ece", "dept": "ECE", "cat": "ON_DUTY",
                "scope": "SPECIFIC_HOURS", "start": today + timedelta(days=2), "end": today + timedelta(days=2),
                "time": "09:30 AM - 12:30 PM",
                "reason": "Keynote Speaker presentation at IEEE International Smart Systems Conference.",
                "hod_remarks": "Approved and forwarded for executive sanction."
            },
            {
                "faculty_uname": "priya.it", "dept": "IT", "cat": "CASUAL",
                "scope": "FULL_DAY", "start": today + timedelta(days=3), "end": today + timedelta(days=3),
                "reason": "Family function and travel to home town.",
                "hod_remarks": "Substitute faculty allotted for III-IT theory period."
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
                session.add(FacultyLeave(
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
                ))

        await session.commit()
        print("\n=== [HYDRATION COMPLETE] AttendTrax Enterprise is 100% Populated & Supabase Ready! ===")


async def ensure_hydrated():
    """Checks if the database has been populated with core roles (e.g. principal)."""
    try:
        await init_db()
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(func.count(User.id))
            user_count = (await session.execute(stmt)).scalar() or 0
            stmt_princ = select(User).where(User.username == "principal")
            princ = (await session.execute(stmt_princ)).scalar_one_or_none()
            if user_count < 10 or not princ:
                print(f"[AUTO-HYDRATION] Database contains {user_count} users. Seeding all departments...")
                await hydrate()
            else:
                print(f"[AUTO-HYDRATION] Database healthy with {user_count} users. Ready!")
    except Exception as e:
        print(f"[AUTO-HYDRATION ERROR] Failed: {e}")


if __name__ == "__main__":
    asyncio.run(hydrate())
