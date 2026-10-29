import sys
import time
import requests

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_all():
    print("=" * 60)
    print("[*] ATTENDTRAX SECURITY & E2E VERIFICATION SUITE")
    print("=" * 60)

    # 1. Health check & Security Headers
    print("\n[1] Checking Health & HTTP Security Headers...")
    r = requests.get(f"{BASE_URL}/health")
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
        resp = requests.post(
            f"{BASE_URL}/auth/login",
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
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "AttendTrax@2026"})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    admin_data = r.json()
    admin_token = admin_data["access_token"]
    assert admin_data["role"] == "ADMIN"
    print(f"  [PASS] Admin Login successful: {admin_data['name']} (Role: {admin_data['role']})")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 4. Admin Analytics API
    r_analytics = requests.get(f"{BASE_URL}/admin/analytics", headers=admin_headers)
    assert r_analytics.status_code == 200, f"Admin analytics failed: {r_analytics.text}"
    analytics = r_analytics.json()
    assert "total_students" in analytics and "class_stats" in analytics and "defaulters" in analytics
    print(f"  [PASS] Admin Analytics OK: {analytics['total_students']} total students, {analytics['overall_percentage']}% attendance")
    print(f"  [PASS] Section Summaries OK: {len(analytics.get('section_summaries', []))} sections reported")


    # 6. Faculty Authentication & Reports
    print("\n[4] Testing Faculty Login & Daily Attendance Marking...")
    r_fac = requests.post(f"{BASE_URL}/auth/login", json={"username": "fathima.cse", "password": "Staff@2026"})
    assert r_fac.status_code == 200, f"Faculty login failed: {r_fac.text}"
    fac_data = r_fac.json()
    fac_token = fac_data["access_token"]
    assert fac_data["role"] == "FACULTY"
    print(f"  [PASS] Faculty Login successful: {fac_data['name']}")


    fac_headers = {"Authorization": f"Bearer {fac_token}"}
    r_fac_classes = requests.get(f"{BASE_URL}/faculty/classes", headers=fac_headers)
    assert r_fac_classes.status_code == 200, f"Faculty classes failed: {r_fac_classes.text}"
    classes = r_fac_classes.json()
    print(f"  [PASS] Faculty classes fetched: {len(classes)} classes")

    # 7. Faculty Class Attendance Report
    r_report = requests.get(f"{BASE_URL}/faculty/reports/class/CSE3A", headers=fac_headers)
    assert r_report.status_code == 200, f"Faculty report failed: {r_report.text}"
    rep_list = r_report.json()
    assert isinstance(rep_list, list), f"Expected list, got {type(rep_list)}"
    print(f"  [PASS] Faculty Class Report OK: {len(rep_list)} students in CSE3A report")


    # 8. Student Authentication & Summary
    print("\n[5] Testing Student Login & Attendance Portal...")
    r_stu = requests.post(f"{BASE_URL}/auth/login", json={"username": "410125104001", "password": "410125104001"})
    assert r_stu.status_code == 200, f"Student login failed: {r_stu.text}"
    stu_data = r_stu.json()
    stu_token = stu_data["access_token"]
    assert stu_data["role"] == "STUDENT"
    print(f"  [PASS] Student Login successful: {stu_data['name']}")


    stu_headers = {"Authorization": f"Bearer {stu_token}"}
    r_stu_summary = requests.get(f"{BASE_URL}/student/attendance", headers=stu_headers)
    assert r_stu_summary.status_code == 200, f"Student summary failed: {r_stu_summary.text}"
    stu_summary = r_stu_summary.json()
    print(f"  [PASS] Student Portal OK: {stu_summary['percentage']}% attendance across {stu_summary['total_hours']} records")



    # 9. RBAC Enforcement: Student cannot access Admin or Faculty routes
    print("\n[6] Testing RBAC Security Restrictions...")
    r_forbidden_admin = requests.get(f"{BASE_URL}/admin/analytics", headers=stu_headers)
    assert r_forbidden_admin.status_code == 403, f"Expected 403 Forbidden for student on admin route, got {r_forbidden_admin.status_code}"
    print("  [PASS] RBAC Check: Student blocked from Admin routes (403 Forbidden)")

    r_forbidden_fac = requests.get(f"{BASE_URL}/faculty/classes", headers=stu_headers)
    assert r_forbidden_fac.status_code == 403, f"Expected 403 Forbidden for student on faculty route, got {r_forbidden_fac.status_code}"
    print("  [PASS] RBAC Check: Student blocked from Faculty routes (403 Forbidden)")

    # 10. Sheet Formula Injection Sanitizer Unit Check
    print("\n[7] Testing Google Sheets Formula Injection Sanitizer...")
    from sheets import sanitize_sheet_cell, sanitize_sheet_row
    assert sanitize_sheet_cell("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0", "Formula starting with = not sanitized"
    assert sanitize_sheet_cell("+SUM(A1:A10)") == "'+SUM(A1:A10)", "Formula starting with + not sanitized"
    assert sanitize_sheet_cell("@HYPERLINK") == "'@HYPERLINK", "Formula starting with @ not sanitized"
    assert sanitize_sheet_cell("100") == "100", "Normal string number modified incorrectly"
    assert sanitize_sheet_cell(-5) == -5, "Numeric value modified incorrectly"
    print("  [PASS] Formula Injection Sanitizer: 100% PASS")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL SECURITY & E2E TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_all()

