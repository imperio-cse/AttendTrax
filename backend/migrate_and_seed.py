# =============================================================================
# AttendTrax Enterprise – Migration & Seed Utility
# migrate_and_seed.py  –  Populate 8 Departments, Roles, and Migrate Data
# =============================================================================
import asyncio
from datetime import datetime, date
from sqlalchemy import select

from database import init_db, get_session_factory
from models import Department, User, ClassRoom, Student, Faculty, Subject
from auth import hash_password


DEPARTMENTS_CONFIG = [
    {"code": "CSE", "name": "Department of Computer Science & Engineering"},
    {"code": "ECE", "name": "Department of Electronics & Communication Engineering"},
    {"code": "EEE", "name": "Department of Electrical & Electronics Engineering"},
    {"code": "MECH", "name": "Department of Mechanical Engineering"},
    {"code": "CIVIL", "name": "Department of Civil Engineering"},
    {"code": "IT", "name": "Department of Information Technology"},
    {"code": "AIDS", "name": "Department of Artificial Intelligence & Data Science"},
    {"code": "CSBS", "name": "Department of Computer Science & Business Systems"},
]


async def seed_enterprise_data():
    print("[INIT] Initializing AttendTrax Enterprise Database schema...")
    await init_db()
    print("[SUCCESS] Tables initialized.")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. Seed 8 Departments
        dept_map = {}
        for d in DEPARTMENTS_CONFIG:
            stmt = select(Department).where(Department.code == d["code"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                dept = Department(code=d["code"], name=d["name"], is_active=True)
                session.add(dept)
                await session.flush()
                dept_map[d["code"]] = dept.id
                print(f"  + Added Department: {d['code']} ({d['name']})")
            else:
                dept_map[d["code"]] = existing.id

        # 2. Seed Super Admin Accounts (Principal, Vice Principal, Central Admin)
        super_admins = [
            {
                "username": "principal",
                "full_name": "Dr. R. Shanmugasundaram (Principal)",
                "password": "Principal@2026",
                "role": "SUPER_ADMIN",
            },
            {
                "username": "viceprincipal",
                "full_name": "Dr. K. Senthil Kumar (Vice Principal)",
                "password": "VP@2026",
                "role": "SUPER_ADMIN",
            },
            {
                "username": "admin",
                "full_name": "Central System Administrator",
                "password": "AttendTrax@2026",
                "role": "SUPER_ADMIN",
            },
        ]

        for sa in super_admins:
            stmt = select(User).where(User.username == sa["username"])
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                user = User(
                    username=sa["username"],
                    password_hash=hash_password(sa["password"]),
                    role=sa["role"],
                    full_name=sa["full_name"],
                    status="ACTIVE",
                )
                session.add(user)
                print(f"  + Added Super Admin: {sa['username']} ({sa['full_name']})")

        # 3. Seed Department HODs for each of the 8 Departments
        for code, dept_id in dept_map.items():
            hod_username = f"hod.{code.lower()}"
            stmt = select(User).where(User.username == hod_username)
            res = await session.execute(stmt)
            hod_user = res.scalar_one_or_none()
            if not hod_user:
                hod_user = User(
                    username=hod_username,
                    password_hash=hash_password("Hod@2026"),
                    role="DEPT_ADMIN",
                    department_id=dept_id,
                    full_name=f"Head of Department ({code})",
                    status="ACTIVE",
                )
                session.add(hod_user)
                await session.flush()
                print(f"  + Added HOD: {hod_username} for {code}")

            # Assign HOD user id to department
            dept_stmt = select(Department).where(Department.id == dept_id)
            d_res = await session.execute(dept_stmt)
            d_obj = d_res.scalar_one_or_none()
            if d_obj:
                d_obj.hod_user_id = hod_user.id

        # 4. Seed Hostel Wardens
        wardens = [
            {"username": "warden.boys", "full_name": "Chief Warden (Boys Hostel)", "password": "Warden@2026"},
            {"username": "warden.girls", "full_name": "Chief Warden (Girls Hostel)", "password": "Warden@2026"},
        ]
        for w in wardens:
            stmt = select(User).where(User.username == w["username"])
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                w_user = User(
                    username=w["username"],
                    password_hash=hash_password(w["password"]),
                    role="WARDEN",
                    full_name=w["full_name"],
                    status="ACTIVE",
                )
                session.add(w_user)
                print(f"  + Added Hostel Warden: {w['username']}")

        # 5. Seed Core CSE Classes (CSE II-A and II-B) if not present
        cse_dept_id = dept_map.get("CSE")
        class_obj_map = {}
        if cse_dept_id:
            cse_classes = [
                {"code": "CSE29A", "name": "CSE II Year A", "year": 2, "section": "A", "semester": 3},
                {"code": "CSE29B", "name": "CSE II Year B", "year": 2, "section": "B", "semester": 3},
            ]
            for c in cse_classes:
                stmt = select(ClassRoom).where(ClassRoom.class_code == c["code"])
                res = await session.execute(stmt)
                cls_obj = res.scalar_one_or_none()
                if not cls_obj:
                    cls_obj = ClassRoom(
                        department_id=cse_dept_id,
                        class_code=c["code"],
                        class_name=c["name"],
                        year=c["year"],
                        section=c["section"],
                        semester=c["semester"],
                        academic_year="2026-2027",
                        status="ACTIVE",
                    )
                    session.add(cls_obj)
                    await session.flush()
                    print(f"  + Added Class: {c['code']} ({c['name']})")
                class_obj_map[c["code"]] = cls_obj.id

        # 6. Migrate existing Students from Sheets into SQL
        try:
            import sheets
            raw_students = sheets.get_all_students()
            migrated_count = 0
            
            # Pre-populate seen_reg_nos with existing records in DB
            stmt = select(Student.reg_no)
            existing_regs = (await session.execute(stmt)).scalars().all()
            seen_reg_nos = set(str(r).strip() for r in existing_regs if r)

            for s in raw_students:
                rn = str(s.get("RegNo", "")).strip()
                if not rn or rn in seen_reg_nos:
                    continue
                s_name = str(s.get("Name", "")).strip()
                cid_str = str(s.get("ClassID", "")).strip()
                matched_cid = class_obj_map.get(cid_str) or list(class_obj_map.values())[0] if class_obj_map else None
                if not matched_cid:
                    continue

                seen_reg_nos.add(rn)

                # Create or fetch student user login
                u_stmt = select(User).where(User.username == rn)
                u_res = await session.execute(u_stmt)
                s_user = u_res.scalar_one_or_none()
                if not s_user:
                    s_user = User(
                        username=rn,
                        password_hash=hash_password(f"{rn}@CSE"),
                        role="STUDENT",
                        department_id=cse_dept_id,
                        full_name=s_name,
                        status="ACTIVE",
                    )
                    session.add(s_user)
                    await session.flush()

                new_student = Student(
                    reg_no=rn,
                    user_id=s_user.id,
                    class_id=matched_cid,
                    department_id=cse_dept_id,
                    name=s_name,
                    residence_type="DAY_SCHOLAR",
                    status="ACTIVE",
                )
                session.add(new_student)
                migrated_count += 1

            if migrated_count:
                print(f"  + Migrated {migrated_count} student records from Google Sheets into PostgreSQL/SQLite.")
            await session.commit()
        except Exception as ex:
            await session.rollback()
            print(f"  [Notice] Sheets student migration skipped/error: {ex}")

        print("\n[COMPLETE] AttendTrax Enterprise database migration and seed completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_enterprise_data())
