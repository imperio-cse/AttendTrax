import os
import sys
import asyncio
import time

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from main import app


async def run_suite():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("=" * 60)
        print("[*] ATTENDTRAX SECURITY & E2E VERIFICATION SUITE")
        print("=" * 60)

        # 1. Health check & Security Headers
        print("\n[1] Checking Health & HTTP Security Headers...")
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.text}"
        assert r.headers.get("X-Content-Type-Options") == "nosniff", "Missing X-Content-Type-Options"
        assert r.headers.get("X-Frame-Options") == "DENY", "Missing X-Frame-Options"
        assert r.headers.get("X-XSS-Protection") == "1; mode=block", "Missing X-XSS-Protection"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin", "Missing Referrer-Policy"
        print("  [PASS] Health: OK")
        print("  [PASS] Security Headers: nosniff, DENY, XSS-filter, strict-origin enforced")

        # 2. Rate Limiting Test on /auth/login
        print("\n[2] Checking Sliding-Window Rate Limiter on /auth/login...")
        test_user = "brute_force_target_test"
        hit_429 = False
        for i in range(1, 8):
            resp = await client.post(
                "/auth/login",
                json={"username": test_user, "password": "WrongPassword123!"},
                headers={"X-Forwarded-For": "203.0.113.195"}
            )
            if resp.status_code == 429:
                hit_429 = True
                retry_after = resp.headers.get("Retry-After")
                print(f"  [PASS] Attempt {i} correctly blocked with HTTP 429 (Retry-After: {retry_after}s)")
                break
            elif resp.status_code == 401:
                print(f"  Attempt {i}: 401 Unauthorized (as expected)")
        assert hit_429, "Rate limiter did not block excessive failed login attempts!"

        # 3. Admin Authentication & RBAC
        print("\n[3] Testing Admin Login & Dashboard Endpoints...")
        r = await client.post("/auth/login", json={"username": "admin", "password": "AttendTrax@2026"})
        assert r.status_code == 200, f"Admin login failed: {r.text}"
        admin_data = r.json()
        admin_token = admin_data["access_token"]
        assert admin_data["role"] in ("ADMIN", "SUPER_ADMIN")
        print(f"  [PASS] Admin Login successful: {admin_data['name']} (Role: {admin_data['role']})")

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # 4. Admin Analytics API
        r_analytics = await client.get("/admin/analytics", headers=admin_headers)
        assert r_analytics.status_code == 200, f"Admin analytics failed: {r_analytics.text}"
        analytics = r_analytics.json()
        assert "total_students" in analytics and "class_stats" in analytics and "defaulters" in analytics
        print(f"  [PASS] Admin Analytics OK: {analytics['total_students']} total students, {analytics['overall_percentage']}% attendance")
        print(f"  [PASS] Section Summaries OK: {len(analytics.get('section_summaries', []))} sections reported")

        # 5. Executive Intelligence Cockpit (Principal / VP)
        print("\n[4] Testing Principal Executive Intelligence Dashboard...")
        r_princ = await client.post("/auth/login", json={"username": "principal", "password": "Principal@2026"})
        assert r_princ.status_code == 200, f"Principal login failed: {r_princ.text}"
        princ_token = r_princ.json()["access_token"]
        princ_headers = {"Authorization": f"Bearer {princ_token}"}

        r_exec = await client.get("/admin/executive/dashboard", headers=princ_headers)
        assert r_exec.status_code == 200, f"Executive dashboard failed: {r_exec.text}"
        exec_data = r_exec.json()
        assert "department_benchmarks" in exec_data and "kpis" in exec_data
        print(f"  [PASS] Executive Cockpit (ALL) OK: {len(exec_data['department_benchmarks'])} departments benchmarked, Total: {exec_data['kpis']['total_students']} students")

        # 5b. Department-Scoped Executive Filtering (CSE vs ECE)
        print("\n[4b] Testing Department-Scoped Filtering in Executive Cockpit...")
        r_exec_cse = await client.get("/admin/executive/dashboard?department_code=CSE", headers=princ_headers)
        assert r_exec_cse.status_code == 200, f"CSE filtered dashboard failed: {r_exec_cse.text}"
        cse_data = r_exec_cse.json()
        assert cse_data["kpis"]["total_students"] <= exec_data["kpis"]["total_students"]
        print(f"  [PASS] CSE Scoped View: {cse_data['kpis']['total_students']} CSE students (No cross-department merging)")

        # 5c. Executive Sanctioned Leaves Archive & Audit Logs
        print("\n[4c] Testing Executive Sanctioned Archive & Audit Trail Ledger...")
        r_archive = await client.get("/admin/executive/leaves/sanctioned-archive", headers=princ_headers)
        assert r_archive.status_code == 200, f"Sanctioned archive failed: {r_archive.text}"
        print(f"  [PASS] Sanctioned Docket Archive: HTTP 200 ({len(r_archive.json())} archived dockets)")

        r_audit = await client.get("/admin/executive/audit-logs", headers=princ_headers)
        assert r_audit.status_code == 200, f"Audit logs failed: {r_audit.text}"
        print(f"  [PASS] Governance Audit Trail: HTTP 200 ({len(r_audit.json())} immutable audit events)")

        # 5d. HOD Authentication & Portal Separation
        print("\n[4d] Testing HOD Portal Separation & Department Admin RBAC...")
        r_hod = await client.post("/auth/login", json={"username": "hod.cse", "password": "Hod@2026"})
        assert r_hod.status_code == 200, f"HOD login failed: {r_hod.text}"
        hod_data = r_hod.json()
        assert hod_data["role"] == "DEPT_ADMIN", f"Expected DEPT_ADMIN role, got {hod_data['role']}"
        hod_headers = {"Authorization": f"Bearer {hod_data['access_token']}"}
        print(f"  [PASS] HOD Login OK: {hod_data['name']} (Role: {hod_data['role']})")

        # HOD must NOT be able to access Super Admin Executive Audit Logs
        r_hod_forbidden_audit = await client.get("/admin/executive/audit-logs", headers=hod_headers)
        assert r_hod_forbidden_audit.status_code == 403, f"Expected 403 Forbidden for HOD on executive audit route, got {r_hod_forbidden_audit.status_code}"
        print("  [PASS] HOD cleanly blocked from Principal Executive Audit logs (403 Forbidden)")

        # 6. Faculty Authentication & Reports
        print("\n[5] Testing Faculty Login & Daily Attendance Marking...")
        r_fac = await client.post("/auth/login", json={"username": "fathima.cse", "password": "Staff@2026"})
        assert r_fac.status_code == 200, f"Faculty login failed: {r_fac.text}"
        fac_data = r_fac.json()
        fac_token = fac_data["access_token"]
        assert fac_data["role"] == "FACULTY"
        print(f"  [PASS] Faculty Login successful: {fac_data['name']}")

        fac_headers = {"Authorization": f"Bearer {fac_token}"}
        r_fac_classes = await client.get("/faculty/classes", headers=fac_headers)
        assert r_fac_classes.status_code == 200, f"Faculty classes failed: {r_fac_classes.text}"
        classes = r_fac_classes.json()
        print(f"  [PASS] Faculty classes fetched: {len(classes)} classes")

        # 7. Faculty Class Attendance Report
        r_report = await client.get("/faculty/reports/class/CSE3A", headers=fac_headers)
        assert r_report.status_code == 200, f"Faculty report failed: {r_report.text}"
        rep_list = r_report.json()
        assert isinstance(rep_list, list), f"Expected list, got {type(rep_list)}"
        print(f"  [PASS] Faculty Class Report OK: {len(rep_list)} students in CSE3A report")

        # 8. Student Authentication & Summary
        print("\n[6] Testing Student Login & Attendance Portal...")
        r_stu = await client.post("/auth/login", json={"username": "410123104041", "password": "410123104041@CSE"})
        assert r_stu.status_code == 200, f"Student login failed: {r_stu.text}"
        stu_data = r_stu.json()
        stu_token = stu_data["access_token"]
        assert stu_data["role"] == "STUDENT"
        print(f"  [PASS] Student Login successful: {stu_data['name']}")

        stu_headers = {"Authorization": f"Bearer {stu_token}"}
        r_stu_summary = await client.get("/student/attendance", headers=stu_headers)
        assert r_stu_summary.status_code == 200, f"Student summary failed: {r_stu_summary.text}"
        stu_summary = r_stu_summary.json()
        print(f"  [PASS] Student Portal OK: {stu_summary['percentage']}% attendance across {stu_summary['total_hours']} records")

        # 9. RBAC Enforcement: Student cannot access Admin or Faculty routes
        print("\n[7] Testing RBAC Security Restrictions...")
        r_forbidden_admin = await client.get("/admin/analytics", headers=stu_headers)
        assert r_forbidden_admin.status_code == 403, f"Expected 403 Forbidden for student on admin route, got {r_forbidden_admin.status_code}"
        print("  [PASS] RBAC Check: Student blocked from Admin routes (403 Forbidden)")

        r_forbidden_fac = await client.get("/faculty/classes", headers=stu_headers)
        assert r_forbidden_fac.status_code == 403, f"Expected 403 Forbidden for student on faculty route, got {r_forbidden_fac.status_code}"
        print("  [PASS] RBAC Check: Student blocked from Faculty routes (403 Forbidden)")

        # 10. Sheet Formula Injection Sanitizer Unit Check
        print("\n[8] Testing Google Sheets Formula Injection Sanitizer...")
        from sheets import sanitize_sheet_cell
        assert sanitize_sheet_cell("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0", "Formula starting with = not sanitized"
        assert sanitize_sheet_cell("+SUM(A1:A10)") == "'+SUM(A1:A10)", "Formula starting with + not sanitized"
        assert sanitize_sheet_cell("@HYPERLINK") == "'@HYPERLINK", "Formula starting with @ not sanitized"
        assert sanitize_sheet_cell("100") == "100", "Normal string number modified incorrectly"
        assert sanitize_sheet_cell(-5) == -5, "Numeric value modified incorrectly"
        print("  [PASS] Formula Injection Sanitizer: 100% PASS")

        print("\n" + "=" * 60)
        print("[SUCCESS] ALL SECURITY & E2E TESTS PASSED 100%!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_suite())
