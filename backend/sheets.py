# =============================================================================
# sheets.py  –  Google Sheets helper layer with High-Performance Caching
# All direct gspread / Google API calls live here.
# =============================================================================
import json, os, re, time, threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound

from config import get_settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Hour labels & schedule ──────────────────────────────────────────────────
HOUR_LABELS = {
    "H1": "H1 (9:00–9:45)",
    "H2": "H2 (9:45–10:30)",
    "H3": "H3 (10:40–11:25)",
    "H4": "H4 (11:25–12:10)",
    "H5": "H5 (12:50–1:35)",
    "H6": "H6 (1:35–2:20)",
    "H7": "H7 (2:30–3:15)",
    "H8": "H8 (3:15–4:00)",
}
ALL_HOURS = list(HOUR_LABELS.keys())   # ['H1', 'H2', ..., 'H8']


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory Cache & Client Handles
# ─────────────────────────────────────────────────────────────────────────────
_client: Optional[gspread.Client] = None
_client_lock = threading.Lock()

_spreadsheet_cache: Dict[str, gspread.Spreadsheet] = {}
_worksheet_cache: Dict[Tuple[str, str], gspread.Worksheet] = {}
_cache_lock = threading.Lock()

# Data Cache: key -> (timestamp, data)
_data_cache: Dict[str, Tuple[float, Any]] = {}
DEFAULT_CACHE_TTL = 60.0  # seconds


def _get_client() -> gspread.Client:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        cfg = get_settings()
        if not cfg.GOOGLE_SERVICE_ACCOUNT_JSON:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON env var is not set.")
        creds_dict = json.loads(cfg.GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _client = gspread.authorize(creds)
        return _client


def _open_by_id(sheet_id: str) -> gspread.Spreadsheet:
    if not sheet_id:
        raise ValueError("Spreadsheet ID is empty.")
    with _cache_lock:
        if sheet_id in _spreadsheet_cache:
            return _spreadsheet_cache[sheet_id]
    
    ss = _get_client().open_by_key(sheet_id)
    with _cache_lock:
        _spreadsheet_cache[sheet_id] = ss
    return ss


def _get_worksheet(sheet_id: str, title: str) -> gspread.Worksheet:
    cache_key = (sheet_id, title)
    with _cache_lock:
        if cache_key in _worksheet_cache:
            return _worksheet_cache[cache_key]
    
    ss = _open_by_id(sheet_id)
    ws = ss.worksheet(title)
    with _cache_lock:
        _worksheet_cache[cache_key] = ws
    return ws


def get_cached(key: str, fetcher, ttl: float = DEFAULT_CACHE_TTL) -> Any:
    now = time.time()
    with _cache_lock:
        if key in _data_cache:
            ts, val = _data_cache[key]
            if now - ts < ttl:
                return val
    # Fetch outside lock to allow concurrency
    fresh_val = fetcher()
    with _cache_lock:
        _data_cache[key] = (time.time(), fresh_val)
    return fresh_val


def invalidate_cache(*keys: str) -> None:
    with _cache_lock:
        if not keys:
            _data_cache.clear()
        else:
            for k in keys:
                _data_cache.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# Date helpers
# ─────────────────────────────────────────────────────────────────────────────
def _date_col_header(d: date) -> str:
    """Returns 'DD-MM-YYYY' string used as the date super-header in class sheets."""
    return d.strftime("%d-%m-%Y")


def _col_letter(n: int) -> str:
    """Convert 1-based column index to A1-notation letter(s)."""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Formula / CSV Injection Sanitizer
# ─────────────────────────────────────────────────────────────────────────────
def sanitize_sheet_cell(val: Any) -> Any:
    """
    Neutralizes CSV / Formula Injection attacks when writing to Google Sheets.
    If a string starts with =, +, -, @, \\t, or \\r, prefix with a single quote (')
    unless it represents a valid numeric value.
    """
    if isinstance(val, str):
        s = val.strip()
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
            try:
                float(s)
                return val
            except ValueError:
                return "'" + val
    return val


def sanitize_sheet_row(row: List[Any]) -> List[Any]:
    return [sanitize_sheet_cell(c) for c in row]


# ─────────────────────────────────────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────────────────────────────────────
def get_all_users() -> List[Dict]:
    """Return all rows from the Users sheet (cached)."""
    def _fetch():
        ws = _get_worksheet(get_settings().USERS_SHEET_ID, "Users")
        return ws.get_all_records()
    return get_cached("users", _fetch, ttl=60.0)


def get_user_by_username(username: str) -> Optional[Dict]:
    users = get_all_users()
    uname = username.strip().lower()
    for u in users:
        if str(u.get("Username", "")).strip().lower() == uname:
            return u
        if str(u.get("UserID", "")).strip().lower() == uname:
            return u
    return None


def create_user(user_data: Dict) -> None:
    ws = _get_worksheet(get_settings().USERS_SHEET_ID, "Users")
    ws.append_row(sanitize_sheet_row([
        user_data["user_id"],
        user_data["name"],
        user_data["username"],
        user_data["password_hash"],
        user_data["role"],
        user_data.get("class_id", ""),
    ]))
    invalidate_cache("users")


def create_users_batch(users_list: List[Dict]) -> int:
    if not users_list:
        return 0
    ws = _get_worksheet(get_settings().USERS_SHEET_ID, "Users")
    rows = [
        sanitize_sheet_row([
            u["user_id"],
            u["name"],
            u["username"],
            u["password_hash"],
            u["role"],
            u.get("class_id", ""),
        ])
        for u in users_list
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    invalidate_cache("users")
    return len(rows)


def get_all_faculty() -> List[Dict]:
    users = get_all_users()
    return [
        {
            "FacultyID": u.get("UserID", ""),
            "Name": u.get("Name", ""),
            "Username": u.get("Username", ""),
            "Role": u.get("Role", ""),
        }
        for u in users
        if str(u.get("Role", "")).upper() == "FACULTY"
    ]


def update_user_password(username: str, new_hash: str) -> bool:
    ws = _get_worksheet(get_settings().USERS_SHEET_ID, "Users")
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):   # row 1 = header
        if str(row.get("Username", "")).strip().lower() == username.strip().lower():
            # Standard order: UserID, Name, Username, PasswordHash, Role, ClassID -> col 4
            col = 4
            if records:
                headers = list(records[0].keys())
                if "PasswordHash" in headers:
                    col = headers.index("PasswordHash") + 1
            ws.update_cell(i, col, new_hash)
            invalidate_cache("users")
            return True
    return False


def delete_user(username: str) -> None:
    ws = _get_worksheet(get_settings().USERS_SHEET_ID, "Users")
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):
        if str(row.get("Username", "")).strip().lower() == username.lower():
            ws.delete_rows(i)
            invalidate_cache("users")
            return


# ─────────────────────────────────────────────────────────────────────────────
# CLASSES & ALIASES
# ─────────────────────────────────────────────────────────────────────────────
CLASS_ALIASES = {
    "CSE4A": ["CSE4A", "CSE27A", "IV", "CSE IV", "CSE IV A", "IV A", "CSE 4A"],
    "CSE27A": ["CSE4A", "CSE27A", "IV", "CSE IV", "CSE IV A", "IV A", "CSE 4A"],
    "CSE3A": ["CSE3A", "CSE28A", "III A", "CSE III A", "CSE 3A"],
    "CSE28A": ["CSE3A", "CSE28A", "III A", "CSE III A", "CSE 3A"],
    "CSE3B": ["CSE3B", "CSE28B", "III B", "CSE III B", "CSE 3B"],
    "CSE28B": ["CSE3B", "CSE28B", "III B", "CSE III B", "CSE 3B"],
    "CSE2A": ["CSE2A", "CSE29A", "II A", "CSE II A", "CSE 2A"],
    "CSE29A": ["CSE2A", "CSE29A", "II A", "CSE II A", "CSE 2A"],
    "CSE2B": ["CSE2B", "CSE29B", "II B", "CSE II B", "CSE 2B"],
    "CSE29B": ["CSE2B", "CSE29B", "II B", "CSE II B", "CSE 2B"],
}


def _classes_match(cid1: str, cid2: str) -> bool:
    """Check if two class IDs match directly or through cohort/alias mapping (e.g. CSE4A <-> CSE27A)."""
    c1 = str(cid1).strip().upper()
    c2 = str(cid2).strip().upper()
    if not c1 or not c2:
        return False
    if c1 == c2:
        return True
    a1 = [a.upper() for a in CLASS_ALIASES.get(c1, [c1])]
    a2 = [a.upper() for a in CLASS_ALIASES.get(c2, [c2])]
    return c2 in a1 or c1 in a2 or bool(set(a1) & set(a2))


def _get_raw_classes() -> List[Dict]:
    def _fetch():
        ws = _get_worksheet(get_settings().CLASSES_SHEET_ID, "Classes")
        return ws.get_all_records()
    return get_cached("classes_raw", _fetch, ttl=60.0)


def get_all_classes() -> List[Dict]:
    return [r for r in _get_raw_classes() if r.get("Status", "").upper() == "ACTIVE"]


def get_class_by_id(class_id: str) -> Optional[Dict]:
    cid = class_id.strip()
    for r in _get_raw_classes():
        if _classes_match(r.get("ClassID", ""), cid):
            return r
    return None


def add_class(data: Dict) -> None:
    ws = _get_worksheet(get_settings().CLASSES_SHEET_ID, "Classes")
    ws.append_row(sanitize_sheet_row([
        data["class_id"],
        data["class_name"],
        data.get("year", ""),
        data.get("section", ""),
        data.get("semester", ""),
        "ACTIVE",
    ]))
    invalidate_cache("classes_raw")


def update_class_name(class_id: str, new_name: str) -> None:
    ws = _get_worksheet(get_settings().CLASSES_SHEET_ID, "Classes")
    records = ws.get_all_records()
    name_col = 2  # ClassName is column 2
    for i, row in enumerate(records, start=2):
        if str(row.get("ClassID", "")).strip() == class_id.strip():
            ws.update_cell(i, name_col, sanitize_sheet_cell(new_name))
            invalidate_cache("classes_raw")
            return


def deactivate_class(class_id: str) -> None:
    ws = _get_worksheet(get_settings().CLASSES_SHEET_ID, "Classes")
    records = ws.get_all_records()
    status_col = 6  # Status is column 6
    for i, row in enumerate(records, start=2):
        if str(row.get("ClassID", "")).strip() == class_id.strip():
            ws.update_cell(i, status_col, "INACTIVE")
            invalidate_cache("classes_raw")
            return


# ─────────────────────────────────────────────────────────────────────────────
# SUBJECTS
# ─────────────────────────────────────────────────────────────────────────────
def _get_raw_subjects() -> List[Dict]:
    def _fetch():
        ws = _get_worksheet(get_settings().SUBJECTS_SHEET_ID, "Subjects")
        return ws.get_all_records()
    return get_cached("subjects_raw", _fetch, ttl=60.0)


def get_all_subjects() -> List[Dict]:
    return [
        r for r in _get_raw_subjects()
        if r.get("Status", "").upper() == "ACTIVE"
    ]


def get_subjects_for_class(class_id: str) -> List[Dict]:
    cid = class_id.strip()
    return [
        r for r in _get_raw_subjects()
        if _classes_match(r.get("ClassID", ""), cid)
        and r.get("Status", "").upper() == "ACTIVE"
    ]


def add_subject(data: Dict) -> None:
    ws = _get_worksheet(get_settings().SUBJECTS_SHEET_ID, "Subjects")
    ws.append_row(sanitize_sheet_row([
        data["subject_id"],
        data["class_id"],
        data["subject_name"],
        data.get("faculty_id", ""),
        "ACTIVE",
    ]))
    invalidate_cache("subjects_raw")


def add_subjects_batch(subjects_list: List[Dict]) -> int:
    if not subjects_list:
        return 0
    ws = _get_worksheet(get_settings().SUBJECTS_SHEET_ID, "Subjects")
    rows = [
        sanitize_sheet_row([
            s["subject_id"],
            s["class_id"],
            s["subject_name"],
            s.get("faculty_id", ""),
            "ACTIVE",
        ])
        for s in subjects_list
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    invalidate_cache("subjects_raw")
    return len(rows)


def delete_subject(subject_id: str) -> None:
    ws = _get_worksheet(get_settings().SUBJECTS_SHEET_ID, "Subjects")
    records = ws.get_all_records()
    status_col = 5  # Status is column 5
    for i, row in enumerate(records, start=2):
        if str(row.get("SubjectID", "")).strip() == subject_id.strip():
            ws.update_cell(i, status_col, "INACTIVE")
            invalidate_cache("subjects_raw")
            return


# ─────────────────────────────────────────────────────────────────────────────
# STUDENTS
# ─────────────────────────────────────────────────────────────────────────────
def _get_raw_students() -> List[Dict]:
    def _fetch():
        ws = _get_worksheet(get_settings().STUDENTS_SHEET_ID, "Students")
        return ws.get_all_records()
    return get_cached("students_raw", _fetch, ttl=60.0)


def get_students_by_class(class_id: str) -> List[Dict]:
    cid = class_id.strip()
    return [
        r for r in _get_raw_students()
        if _classes_match(r.get("ClassID", ""), cid)
        and r.get("Status", "").upper() == "ACTIVE"
    ]


def get_all_students() -> List[Dict]:
    return _get_raw_students()


def get_student_by_regnum(reg_num: str) -> Optional[Dict]:
    rnum = reg_num.strip().lower()
    for r in _get_raw_students():
        if str(r.get("RegNo", "")).strip().lower() == rnum:
            return r
    return None


def add_student(data: Dict) -> None:
    ws = _get_worksheet(get_settings().STUDENTS_SHEET_ID, "Students")
    ws.append_row(sanitize_sheet_row([
        data["reg_no"],
        data["name"],
        data["class_id"],
        data.get("class_name", ""),
        "ACTIVE",
    ]))
    invalidate_cache("students_raw")
    # Also add to class attendance sheet
    _ensure_student_in_class_sheet(data["class_id"], data["reg_no"], data["name"])


def add_students_batch(students_list: List[Dict]) -> int:
    if not students_list:
        return 0
    ws = _get_worksheet(get_settings().STUDENTS_SHEET_ID, "Students")
    rows = [
        sanitize_sheet_row([
            s["reg_no"],
            s["name"],
            s["class_id"],
            s.get("class_name", ""),
            "ACTIVE",
        ])
        for s in students_list
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    invalidate_cache("students_raw")
    # Also update class sheets
    for s in students_list:
        try:
            _ensure_student_in_class_sheet(s["class_id"], s["reg_no"], s["name"])
        except Exception:
            pass
    return len(rows)


def deactivate_student(reg_no: str) -> None:
    ws = _get_worksheet(get_settings().STUDENTS_SHEET_ID, "Students")
    records = ws.get_all_records()
    status_col = 5  # Status is column 5
    for i, row in enumerate(records, start=2):
        if str(row.get("RegNo", "")).strip() == reg_no.strip():
            ws.update_cell(i, status_col, "INACTIVE")
            invalidate_cache("students_raw")
            return


# ─────────────────────────────────────────────────────────────────────────────
# CLASS ATTENDANCE SHEETS
# ─────────────────────────────────────────────────────────────────────────────
def _get_class_spreadsheet(class_id: str) -> gspread.Spreadsheet:
    """Return the Spreadsheet for the given class via SpreadsheetID in Classes sheet or setup_sheets."""
    records = _get_raw_classes()
    cid = str(class_id).strip()
    for row in records:
        if _classes_match(row.get("ClassID", ""), cid):
            sid = str(row.get("SpreadsheetID", "")).strip()
            if sid:
                return _open_by_id(sid)
    # Fallback lookup in setup_sheets.SHEET_IDS
    try:
        from setup_sheets import SHEET_IDS
        if cid in SHEET_IDS and SHEET_IDS[cid].strip():
            return _open_by_id(SHEET_IDS[cid].strip())
        for alias in CLASS_ALIASES.get(cid.upper(), []):
            if alias in SHEET_IDS and SHEET_IDS[alias].strip():
                return _open_by_id(SHEET_IDS[alias].strip())
    except Exception:
        pass
    raise ValueError(f"No SpreadsheetID configured for class '{class_id}' in Classes sheet or setup_sheets.py.")


def _get_class_id_for_spreadsheet(spreadsheet_id: str) -> Optional[str]:
    """Reverse lookup: given a spreadsheet ID, return its ClassID."""
    try:
        for row in _get_raw_classes():
            if str(row.get("SpreadsheetID", "")).strip() == spreadsheet_id.strip():
                return str(row.get("ClassID", "")).strip()
    except Exception:
        pass
    try:
        from setup_sheets import SHEET_IDS
        for cid, sid in SHEET_IDS.items():
            if sid.strip() == spreadsheet_id.strip():
                return cid
    except Exception:
        pass
    return None


STUDENT_DATA_START_ROW = 3   # fixed row 3 for student attendance


def _get_or_create_month_worksheet(spreadsheet: gspread.Spreadsheet, month_label: str) -> gspread.Worksheet:
    """Return (or create) a worksheet named e.g. 'Sep-2026'."""
    try:
        return spreadsheet.worksheet(month_label)
    except WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=month_label, rows=300, cols=300)
        ws.update("A1:B2", [["Reg No", "Student Name"], ["", ""]])
        ws.format("A1:B1", {"textFormat": {"bold": True}})

        class_id = _get_class_id_for_spreadsheet(spreadsheet.id)
        if class_id:
            all_students = _get_raw_students()
            rows = [
                [s["RegNo"], s["Name"]]
                for s in all_students
                if str(s.get("ClassID", "")).strip() == class_id
                and s.get("Status", "").upper() == "ACTIVE"
            ]
            if rows:
                ws.update(
                    f"A{STUDENT_DATA_START_ROW}:B{STUDENT_DATA_START_ROW - 1 + len(rows)}",
                    rows
                )
        return ws


def _find_or_create_date_hour_col(ws: gspread.Worksheet, date_str: str, hour: str = "DAY") -> int:
    """Finds or creates the date column in the daily attendance register."""
    row2 = ws.row_values(2)
    row1 = ws.row_values(1)

    # 1. Check if date_str is already in row 2 (daily format)
    target_d = date_str.strip()
    # Normalize variants like "1-10-2026" vs "01-10-2026"
    for idx, val in enumerate(row2):
        if idx < 2:
            continue
        v = val.strip()
        if v == target_d:
            return idx + 1
        try:
            if datetime.strptime(v, "%d-%m-%Y") == datetime.strptime(target_d, "%d-%m-%Y"):
                return idx + 1
        except Exception:
            pass

    # 2. Check in row 1 (fallback)
    for idx, val in enumerate(row1):
        if idx < 2:
            continue
        if val.strip() == target_d:
            return idx + 1

    # 3. If not found, place before summary columns if present, or at the end
    insert_idx = len(row2)
    for idx, val in enumerate(row2):
        if "total present" in val.strip().lower() or "total" in val.strip().lower():
            insert_idx = idx
            break

    ws.update_cell(2, insert_idx + 1, target_d)
    cl = _col_letter(insert_idx + 1)
    ws.format(f"{cl}2", {
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "backgroundColor": {"red": 0.231, "green": 0.510, "blue": 0.965},
        "horizontalAlignment": "CENTER",
    })
    return insert_idx + 1



def _ensure_student_in_class_sheet(class_id: str, reg_no: str, name: str) -> None:
    try:
        ss = _get_class_spreadsheet(class_id)
    except ValueError:
        return
    for ws in ss.worksheets():
        col_a_full = ws.col_values(1)
        student_reg_nums = col_a_full[STUDENT_DATA_START_ROW - 1:]
        if reg_no not in student_reg_nums:
            next_row = max(STUDENT_DATA_START_ROW, len(col_a_full) + 1)
            ws.update(f"A{next_row}:B{next_row}", [[reg_no, name]])


def get_students_for_attendance(class_id: str) -> List[Dict]:
    return [
        {"reg_no": r["RegNo"], "name": r["Name"]}
        for r in get_students_by_class(class_id)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE LOG (Cached for Instant Immuntability & Reporting)
# ─────────────────────────────────────────────────────────────────────────────
def _get_raw_attendance_log() -> List[Dict]:
    def _fetch():
        ws = _get_worksheet(get_settings().ATTENDANCE_LOG_SHEET_ID, "Attendance_Log")
        return ws.get_all_records()
    return get_cached("attendance_log_raw", _fetch, ttl=30.0)


def check_attendance_exists(class_id: str, date_str: str, hour: str, subject_id: str = "") -> bool:
    records = _get_raw_attendance_log()
    cid = class_id.strip()
    dstr = date_str.strip()
    hr = hour.strip().upper()
    sid = subject_id.strip()
    for r in records:
        r_cid = str(r.get("ClassID", "")).strip()
        r_date = str(r.get("Date", "")).strip()
        r_hr = str(r.get("Hour", "")).strip().upper()
        r_sid = str(r.get("SubjectID", "")).strip()
        if _classes_match(r_cid, cid) and _match_dates(r_date, dstr) and (not hr or r_hr == hr or hr == "DAY"):
            if not sid or r_sid == sid:
                return True
    return False


def save_attendance(
    class_id: str,
    date_str: str,
    hour: str,
    subject_id: str,
    faculty_id: str,
    attendance: Dict[str, str],   # {reg_no: "P"/"A"/"-"}
) -> None:
    # ── 1. Visual class sheet ──────────────────────────────────────────────
    try:
        ss = _get_class_spreadsheet(class_id)
        month_label = datetime.strptime(date_str, "%d-%m-%Y").strftime("%b-%Y")
        ws = _get_or_create_month_worksheet(ss, month_label)

        col_idx = _find_or_create_date_hour_col(ws, date_str, hour)

        col_a_full = ws.col_values(1)
        reg_to_row: Dict[str, int] = {}
        for i, val in enumerate(col_a_full):
            if i >= STUDENT_DATA_START_ROW - 1 and val.strip():
                reg_to_row[val.strip()] = i + 1

        updates = []
        for reg_no, status in attendance.items():
            row_idx = reg_to_row.get(reg_no.strip())
            if row_idx is None:
                continue
            updates.append({
                "range": f"{_col_letter(col_idx)}{row_idx}",
                "values": [[status]],
            })
        if updates:
            ws.batch_update(updates)
    except Exception as ex:
        # Visual sheet error logged but doesn't crash log storage
        print(f"[Warning] Failed to update visual sheet for {class_id}: {ex}")

    # ── 2. Attendance_Log ─────────────────────────────────────────────────
    log_ws = _get_worksheet(get_settings().ATTENDANCE_LOG_SHEET_ID, "Attendance_Log")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for reg_no, status in attendance.items():
        rows.append(sanitize_sheet_row([
            "",
            date_str,
            class_id,
            hour,
            subject_id,
            reg_no,
            status,
            faculty_id,
            now_str,
        ]))
    if rows:
        log_ws.append_rows(rows, value_input_option="USER_ENTERED")
    
    invalidate_cache("attendance_log_raw")


def _match_dates(d1: str, d2: str) -> bool:
    """Helper to match dates across formats (DD-MM-YYYY, YYYY-MM-DD, D/M/YYYY, etc.)."""
    s1 = str(d1).strip().replace("/", "-")
    s2 = str(d2).strip().replace("/", "-")
    if not s1 or not s2:
        return False
    if s1 == s2:
        return True
    p1 = s1.split("-")
    p2 = s2.split("-")
    if len(p1) == 3 and len(p2) == 3:
        try:
            if len(p1[0]) == 4:
                y1, m1, day1 = int(p1[0]), int(p1[1]), int(p1[2])
            else:
                y1, m1, day1 = int(p1[2]), int(p1[1]), int(p1[0])

            if len(p2[0]) == 4:
                y2, m2, day2 = int(p2[0]), int(p2[1]), int(p2[2])
            else:
                y2, m2, day2 = int(p2[2]), int(p2[1]), int(p2[0])

            return y1 == y2 and m1 == m2 and day1 == day2
        except Exception:
            pass
    return False


def get_daily_attendance_for_edit(
    class_id: str,
    date_str: str,
    hour: str = "DAY",
    subject_id: str = "",
) -> Dict[str, Any]:
    """Retrieve students and their existing attendance status for the given class, date, hour, and subject."""
    cid = class_id.strip()
    dstr = date_str.strip()
    hr = (hour or "DAY").strip().upper()
    sid = subject_id.strip()

    students = get_students_by_class(cid)
    records = _get_raw_attendance_log()
    all_users = get_all_users()

    # Find existing matching log records
    matching_records: Dict[str, Dict] = {}
    faculty_id = ""
    last_timestamp = ""

    for r in records:
        r_cid = str(r.get("ClassID", "")).strip()
        r_date = str(r.get("Date", "")).strip()
        r_hr = str(r.get("Hour", "")).strip().upper()
        r_sid = str(r.get("SubjectID", "")).strip()
        r_reg = str(r.get("RegNo", "")).strip()

        if _classes_match(r_cid, cid) and _match_dates(r_date, dstr) and (not hr or r_hr == hr or hr == "DAY"):
            if not sid or not r_sid or r_sid == sid:
                matching_records[r_reg] = r
                if not faculty_id:
                    faculty_id = str(r.get("FacultyID", "")).strip()
                last_timestamp = str(r.get("Timestamp", "")).strip()

    is_submitted = len(matching_records) > 0

    faculty_name = faculty_id or "Faculty Staff"
    for u in all_users:
        uid = str(u.get("UserID", "")).strip()
        uname = str(u.get("Username", "")).strip()
        if (uid and uid == faculty_id) or (uname and uname == faculty_id):
            faculty_name = str(u.get("Name", "")).strip() or faculty_id
            break

    student_entries = []
    for s in students:
        reg_no = str(s.get("RegNo", "")).strip()
        name = str(s.get("Name", "")).strip()
        status_val = matching_records.get(reg_no, {}).get("Status", "P") if is_submitted else "P"
        student_entries.append({
            "reg_no": reg_no,
            "name": name,
            "status": status_val if status_val in ("P", "A", "OD", "-") else "P"
        })

    return {
        "class_id": cid,
        "date": dstr,
        "hour": hr,
        "subject_id": sid,
        "faculty_id": faculty_id,
        "faculty_name": faculty_name,
        "last_timestamp": last_timestamp,
        "is_submitted": is_submitted,
        "students": student_entries,
    }


def admin_update_attendance(
    class_id: str,
    date_str: str,
    hour: str,
    subject_id: str,
    admin_id: str,
    attendance: Dict[str, str],   # {reg_no: "P"/"A"/"OD"}
) -> Dict[str, Any]:
    """Admin overwrite and update of daily attendance in both visual spreadsheet and master Attendance_Log."""
    cid = class_id.strip()
    dstr = date_str.strip()
    hr = (hour or "DAY").strip().upper()
    sid = subject_id.strip()

    # ── 1. Update visual class monthly worksheet ─────────────────────────────
    try:
        ss = _get_class_spreadsheet(cid)
        month_label = datetime.strptime(dstr, "%d-%m-%Y").strftime("%b-%Y")
        ws = _get_or_create_month_worksheet(ss, month_label)

        col_idx = _find_or_create_date_hour_col(ws, dstr, hr)

        col_a_full = ws.col_values(1)
        reg_to_row: Dict[str, int] = {}
        for i, val in enumerate(col_a_full):
            if i >= STUDENT_DATA_START_ROW - 1 and val.strip():
                reg_to_row[val.strip()] = i + 1

        updates = []
        for reg_no, status in attendance.items():
            row_idx = reg_to_row.get(reg_no.strip())
            if row_idx is None:
                continue
            updates.append({
                "range": f"{_col_letter(col_idx)}{row_idx}",
                "values": [[status]],
            })
        if updates:
            ws.batch_update(updates)
    except Exception as ex:
        print(f"[Warning] Failed to update visual sheet for {cid}: {ex}")

    # ── 2. Update Master Attendance_Log ─────────────────────────────────────
    log_ws = _get_worksheet(get_settings().ATTENDANCE_LOG_SHEET_ID, "Attendance_Log")
    all_rows = log_ws.get_all_values()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Header is at index 0
    # Columns: LogID (0), Date (1), ClassID (2), Hour (3), SubjectID (4), RegNo (5), Status (6), FacultyID (7), Timestamp (8)
    cell_updates = []
    matched_reg_nos = set()

    canonical_cid = _find_canonical_cid(cid) or cid

    for row_idx, row in enumerate(all_rows[1:], start=2):
        if len(row) < 7:
            continue
        r_date = row[1].strip()
        r_cid = row[2].strip()
        r_hr = row[3].strip().upper()
        r_sid = row[4].strip() if len(row) > 4 else ""
        r_reg = row[5].strip() if len(row) > 5 else ""

        if _classes_match(r_cid, cid) and _match_dates(r_date, dstr):
            if not hr or hr in ("DAY", "DAILY") or r_hr in (hr, "DAY", "DAILY"):
                if not sid or not r_sid or r_sid == sid:
                    if r_reg in attendance:
                        new_st = attendance[r_reg]
                        matched_reg_nos.add(r_reg)
                        # Update status in Col G (col 7)
                        cell_updates.append({
                            "range": f"G{row_idx}",
                            "values": [[new_st]]
                        })
                        # Update timestamp in Col I (col 9)
                        cell_updates.append({
                            "range": f"I{row_idx}",
                            "values": [[f"{now_str} (Modified by Admin: {admin_id})"]]
                        })
                        if sid and (len(row) <= 4 or not row[4].strip()):
                            cell_updates.append({
                                "range": f"E{row_idx}",
                                "values": [[sid]]
                            })

    if cell_updates:
        log_ws.batch_update(cell_updates)

    # Any students not yet in log rows get appended
    missing_reg_nos = [r for r in attendance if r not in matched_reg_nos]
    if missing_reg_nos:
        new_rows = []
        for reg_no in missing_reg_nos:
            new_rows.append(sanitize_sheet_row([
                "",
                dstr,
                canonical_cid,
                hr,
                sid or "GENERAL",
                reg_no,
                attendance[reg_no],
                f"Admin: {admin_id}",
                now_str,
            ]))
        log_ws.append_rows(new_rows, value_input_option="USER_ENTERED")

    invalidate_cache()
    return {
        "message": f"Daily attendance for {cid} on {dstr} ({hr}) successfully updated by Admin.",
        "updated_count": len(attendance),
        "date": dstr,
        "class_id": cid,
    }


def get_date_attendance_overview(date_str: str, force_refresh: bool = True) -> Dict[str, Any]:
    """
    Get full institutional attendance overview for a specific date:
    - Lists all submitted sessions with faculty name, subject, and student stats.
    - Lists all classes that have not yet submitted attendance for that date.
    """
    if force_refresh:
        invalidate_cache("attendance_log_raw")
    dstr = date_str.strip()
    classes = get_all_classes()
    all_users = get_all_users()
    subjects = _get_raw_subjects()
    records = _get_raw_attendance_log()

    # Map faculty ID / Username to Faculty Full Name
    faculty_map: Dict[str, str] = {}
    for u in all_users:
        uid = str(u.get("UserID", "")).strip()
        uname = str(u.get("Username", "")).strip()
        name = str(u.get("Name", "")).strip()
        if uid and name:
            faculty_map[uid] = name
        if uname and name:
            faculty_map[uname] = name

    # Map SubjectID to Subject Name
    sub_name_map = {str(s.get("SubjectID", "")).strip(): str(s.get("SubjectName", "")).strip() for s in subjects}
    class_map = {str(c.get("ClassID", "")).strip(): c for c in classes}

    # Filter log records for the given date using tolerant matching
    date_records = [r for r in records if _match_dates(str(r.get("Date", "")), dstr)]

    # Group by (class_id, hour, subject_id)
    grouped: Dict[Tuple[str, str, str], List[Dict]] = {}
    for r in date_records:
        cid = str(r.get("ClassID", "")).strip()
        hr = str(r.get("Hour", "")).strip().upper() or "DAY"
        sid = str(r.get("SubjectID", "")).strip()
        key = (cid, hr, sid)
        grouped.setdefault(key, []).append(r)

    submitted_sessions = []
    submitted_class_ids = set()

    for (cid, hr, sid), rows in grouped.items():
        submitted_class_ids.add(cid)
        cls = class_map.get(cid, {})
        cname = cls.get("ClassName", cid)
        year = cls.get("Year", "")
        section = cls.get("Section", "")
        sem = cls.get("Semester", "")

        first_row = rows[0]
        raw_fac_id = str(first_row.get("FacultyID", "")).strip()
        fac_name = faculty_map.get(raw_fac_id, raw_fac_id or "Faculty Staff")
        timestamp = str(first_row.get("Timestamp", "")).strip()

        p_count = sum(1 for r in rows if str(r.get("Status", "")).upper() == "P")
        a_count = sum(1 for r in rows if str(r.get("Status", "")).upper() == "A")
        od_count = sum(1 for r in rows if str(r.get("Status", "")).upper() == "OD")
        total_marked = p_count + a_count + od_count
        pct = round(p_count / total_marked * 100, 1) if total_marked else 0.0

        sub_display = sub_name_map.get(sid, sid) if sid else "Daily Attendance"

        submitted_sessions.append({
            "class_id": cid,
            "class_name": cname,
            "year": year,
            "section": section,
            "semester": sem,
            "hour": hr,
            "subject_id": sid,
            "subject_name": sub_display,
            "faculty_id": raw_fac_id,
            "faculty_name": fac_name,
            "timestamp": timestamp,
            "present": p_count,
            "absent": a_count,
            "on_duty": od_count,
            "total_students": total_marked,
            "percentage": pct,
        })

    # Sort submitted sessions by class_name / hour
    submitted_sessions.sort(key=lambda x: (x["class_name"], x["hour"]))

    # Find pending classes (classes that haven't submitted any attendance on this date)
    pending_classes = []
    for cls in classes:
        cid = str(cls.get("ClassID", "")).strip()
        if cid not in submitted_class_ids:
            st_count = len(get_students_by_class(cid))
            pending_classes.append({
                "class_id": cid,
                "class_name": cls.get("ClassName", cid),
                "year": cls.get("Year", ""),
                "section": cls.get("Section", ""),
                "semester": cls.get("Semester", ""),
                "student_count": st_count,
            })

    pending_classes.sort(key=lambda x: x["class_name"])

    return {
        "date": dstr,
        "total_classes": len(classes),
        "submitted_count": len(submitted_sessions),
        "pending_count": len(pending_classes),
        "submitted": submitted_sessions,
        "pending": pending_classes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT ATTENDANCE SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def get_student_attendance_summary(reg_no: str) -> Dict:
    records = _get_raw_attendance_log()
    rn = reg_no.strip()
    student_rows = [r for r in records if str(r.get("RegNo", "")).strip() == rn]

    valid_rows = [r for r in student_rows if str(r.get("Status", "")).strip().upper() in ("P", "A", "OD", "ONDUTY", "ON DUTY")]
    total = len(valid_rows)
    attended = len([r for r in valid_rows if str(r.get("Status", "")).strip().upper() == "P"])
    od = len([r for r in valid_rows if str(r.get("Status", "")).strip().upper() in ("OD", "ONDUTY", "ON DUTY")])
    effective_attended = attended + od

    subject_stats: Dict[str, Dict[str, int]] = {}
    for r in student_rows:
        st = str(r.get("Status", "")).strip().upper()
        if st not in ("P", "A", "OD", "ONDUTY", "ON DUTY"):
            continue
        sid = str(r.get("SubjectID", ""))
        if sid not in subject_stats:
            subject_stats[sid] = {"total": 0, "attended": 0, "od": 0}
        subject_stats[sid]["total"] += 1
        if st == "P":
            subject_stats[sid]["attended"] += 1
        elif st in ("OD", "ONDUTY", "ON DUTY"):
            subject_stats[sid]["od"] += 1

    sub_records = _get_raw_subjects()
    sub_name_map = {str(r["SubjectID"]): r["SubjectName"] for r in sub_records}

    subject_summary = []
    for sid, stats in subject_stats.items():
        eff_sub = stats["attended"] + stats.get("od", 0)
        pct = round(eff_sub / stats["total"] * 100, 2) if stats["total"] else 0.0
        subject_summary.append({
            "subject_id": sid,
            "subject_name": sub_name_map.get(sid, sid),
            "total": stats["total"],
            "attended": stats["attended"],
            "od": stats.get("od", 0),
            "percentage": pct,
        })

    overall_pct = round(effective_attended / total * 100, 2) if total else 0.0

    date_hour_map: Dict[str, Dict[str, str]] = {}
    for r in student_rows:
        d = str(r.get("Date", ""))
        h = str(r.get("Hour", ""))
        if d not in date_hour_map:
            date_hour_map[d] = {}
        date_hour_map[d][h] = r.get("Status", "-")

    datewise = []
    for d in sorted(date_hour_map.keys()):
        row_dict = {"date": d}
        for h in ALL_HOURS:
            row_dict[h] = date_hour_map[d].get(h, "-")
        datewise.append(row_dict)

    return {
        "total_hours": total,
        "attended_hours": attended,
        "od_hours": od,
        "percentage": overall_pct,
        "subject_summary": subject_summary,
        "datewise": datewise[-60:],
    }


# ─────────────────────────────────────────────────────────────────────────────
# PAST ATTENDANCE IMPORT
# ─────────────────────────────────────────────────────────────────────────────
def import_past_attendance_rows(rows: List[Dict]) -> int:
    log_ws = _get_worksheet(get_settings().ATTENDANCE_LOG_SHEET_ID, "Attendance_Log")
    existing = _get_raw_attendance_log()
    existing_keys = {
        (str(r["Date"]), str(r["ClassID"]), str(r["Hour"]), str(r["SubjectID"]), str(r["RegNo"]))
        for r in existing
    }

    new_rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        key = (row["date"], row["class_id"], row["hour"], row["subject_id"], row["reg_no"])
        if key not in existing_keys:
            new_rows.append([
                "",
                row["date"],
                row["class_id"],
                row["hour"],
                row["subject_id"],
                row["reg_no"],
                row["status"],
                row.get("faculty_id", "IMPORT"),
                now_str,
            ])
            existing_keys.add(key)

    if new_rows:
        log_ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        invalidate_cache("attendance_log_raw")

    return len(new_rows)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – Reports
# ─────────────────────────────────────────────────────────────────────────────
def get_class_attendance_report(class_id: str) -> List[Dict]:
    students = get_students_by_class(class_id)
    records = _get_raw_attendance_log()
    cid = class_id.strip()
    class_rows = [r for r in records if _classes_match(r.get("ClassID", ""), cid)]

    # Batch/Level unified date determination
    all_classes = get_all_classes()
    curr_class = next((c for c in all_classes if _classes_match(c.get("ClassID", ""), cid)), {})
    year_val = str(curr_class.get("Year", "")).strip()

    batch_class_ids = [
        str(c["ClassID"]).strip()
        for c in all_classes
        if str(c.get("Year", "")).strip() == year_val
    ] if year_val else [cid]

    batch_rows = [r for r in records if any(_classes_match(r.get("ClassID", ""), bc) for bc in batch_class_ids)]
    batch_working_dates = {
        str(r.get("Date", "")).strip()
        for r in batch_rows
        if str(r.get("Date", "")).strip() and str(r.get("Status", "")).strip().upper() in ("P", "A", "OD", "ONDUTY", "ON DUTY")
    }

    class_working_dates = {
        str(r.get("Date", "")).strip()
        for r in class_rows
        if str(r.get("Date", "")).strip() and str(r.get("Status", "")).strip().upper() in ("P", "A", "OD", "ONDUTY", "ON DUTY")
    }
    unified_working_days = max(len(class_working_dates), len(batch_working_dates))

    result = []
    for s in students:
        rn = str(s["RegNo"])
        student_rows = [r for r in class_rows if str(r.get("RegNo", "")).strip() == rn]
        student_working_dates = {
            str(r.get("Date", "")).strip()
            for r in student_rows
            if str(r.get("Date", "")).strip() and str(r.get("Status", "")).strip().upper() in ("P", "A", "OD", "ONDUTY", "ON DUTY")
        }
        working_days = max(len(student_working_dates), unified_working_days)

        attended = len([r for r in student_rows if str(r.get("Status", "")).strip().upper() == "P"])
        absent = len([r for r in student_rows if str(r.get("Status", "")).strip().upper() == "A"])
        od = len([r for r in student_rows if str(r.get("Status", "")).strip().upper() in ("OD", "ONDUTY", "ON DUTY")])
        total = attended + absent + od

        # Treat OD as present
        effective_attended = attended + od
        pct = round((effective_attended / total) * 100, 2) if total else 0.0

        result.append({
            "reg_no": rn,
            "name": s["Name"],
            "working_days": working_days,
            "total": total,
            "attended": attended,
            "absent": absent,
            "od": od,
            "percentage": pct,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – Comprehensive Dashboard Analytics
# ─────────────────────────────────────────────────────────────────────────────
def get_admin_analytics(force_refresh: bool = True) -> Dict[str, Any]:
    active_classes = get_all_classes()
    class_map = {str(c["ClassID"]).strip(): str(c.get("ClassName", c["ClassID"])).strip() for c in active_classes}
    active_students = [s for s in _get_raw_students() if s.get("Status", "").upper() == "ACTIVE"]
    student_map = {str(s["RegNo"]).strip(): s for s in active_students}
    active_subjects = [s for s in _get_raw_subjects() if s.get("Status", "").upper() == "ACTIVE"]
    faculty_users = [u for u in get_all_users() if str(u.get("Role", "")).upper() == "FACULTY"]
    
    if force_refresh:
        invalidate_cache("attendance_log_raw")
    logs = _get_raw_attendance_log()
    today_str = date.today().strftime("%d-%m-%Y")
    
    # Helper to resolve raw ClassID in log to canonical active class ID
    def _find_canonical_cid(raw_cid: str) -> Optional[str]:
        rc = str(raw_cid).strip()
        for cid in class_map.keys():
            if _classes_match(rc, cid):
                return cid
        return None

    # Filter overall logs (including OD)
    total_records = len(logs)
    valid_logs = [r for r in logs if str(r.get("Status", "")).strip().upper() in ("P", "A", "OD", "ONDUTY", "ON DUTY")]
    total_hours = len(valid_logs)
    attended_hours = len([r for r in valid_logs if str(r.get("Status", "")).strip().upper() == "P"])
    od_hours = len([r for r in valid_logs if str(r.get("Status", "")).strip().upper() in ("OD", "ONDUTY", "ON DUTY")])
    effective_attended_hours = attended_hours + od_hours
    overall_percentage = round((effective_attended_hours / total_hours) * 100, 1) if total_hours else 0.0

    # Today's overall attendance telemetry
    all_today_logs = [
        r for r in logs
        if _match_dates(str(r.get("Date", "")), today_str)
    ]
    today_present = len([r for r in all_today_logs if str(r.get("Status", "")).strip().upper() == "P"])
    today_absent = len([r for r in all_today_logs if str(r.get("Status", "")).strip().upper() == "A"])
    today_od = len([r for r in all_today_logs if str(r.get("Status", "")).strip().upper() in ("OD", "-", "ONDUTY", "ON DUTY")])
    today_total = len(all_today_logs)
    today_effective = today_present + today_absent + today_od
    today_percentage = round(((today_present + today_od) / today_effective) * 100, 1) if today_effective else 0.0

    status_distribution = {
        "present": attended_hours,
        "absent": total_hours - effective_attended_hours,
        "on_duty": od_hours,
    }

    class_info_map = {str(c["ClassID"]).strip(): c for c in active_classes}
    subject_map = {str(s.get("SubjectID", "")).strip(): s.get("SubjectName", s.get("SubjectID", "")) for s in active_subjects}

    # Pre-calculate defaulters per student (treating OD as Present)
    student_att_map = {}
    for r in valid_logs:
        rn = str(r.get("RegNo", "")).strip()
        if not rn:
            continue
        if rn not in student_att_map:
            student_att_map[rn] = {"total": 0, "attended": 0, "od": 0}
        student_att_map[rn]["total"] += 1
        st = str(r.get("Status", "")).strip().upper()
        if st == "P":
            student_att_map[rn]["attended"] += 1
        elif st in ("OD", "ONDUTY", "ON DUTY"):
            student_att_map[rn]["od"] += 1

    defaulters = []
    class_defaulter_count = {cid: 0 for cid in class_map.keys()}
    for rn, s in student_map.items():
        st = student_att_map.get(rn, {"total": 0, "attended": 0, "od": 0})
        effective = st["attended"] + st["od"]
        pct = round((effective / st["total"]) * 100, 1) if st["total"] else 0.0
        raw_cid = str(s.get("ClassID", "")).strip()
        cid = _find_canonical_cid(raw_cid) or raw_cid
        if st["total"] > 0 and pct < 75.0:
            if cid in class_defaulter_count:
                class_defaulter_count[cid] += 1
            defaulters.append({
                "reg_no": rn,
                "name": s.get("Name", rn),
                "class_id": cid,
                "class_name": class_map.get(cid, cid),
                "total": st["total"],
                "attended": st["attended"],
                "absent": st["total"] - effective,
                "od": st["od"],
                "percentage": pct,
            })
    defaulters.sort(key=lambda x: x["percentage"])

    # Class & Section wise aggregation
    class_stat_map = {
        cid: {
            "total": 0, "attended": 0, "absent": 0, "on_duty": 0,
            "today_total": 0, "today_present": 0, "today_absent": 0, "today_od": 0,
            "subjects": {}
        }
        for cid in class_map.keys()
    }

    for r in logs:
        raw_cid = str(r.get("ClassID", "")).strip()
        cid = _find_canonical_cid(raw_cid)
        if not cid or cid not in class_stat_map:
            continue
        st_code = str(r.get("Status", "")).strip().upper()
        d_str = str(r.get("Date", "")).strip()
        sub_id = str(r.get("SubjectID", "")).strip()

        is_today = _match_dates(d_str, today_str)

        if st_code == "P":
            class_stat_map[cid]["total"] += 1
            class_stat_map[cid]["attended"] += 1
            if is_today:
                class_stat_map[cid]["today_total"] += 1
                class_stat_map[cid]["today_present"] += 1
            if sub_id:
                if sub_id not in class_stat_map[cid]["subjects"]:
                    class_stat_map[cid]["subjects"][sub_id] = {"total": 0, "attended": 0, "od": 0}
                class_stat_map[cid]["subjects"][sub_id]["total"] += 1
                class_stat_map[cid]["subjects"][sub_id]["attended"] += 1
        elif st_code == "A":
            class_stat_map[cid]["total"] += 1
            class_stat_map[cid]["absent"] += 1
            if is_today:
                class_stat_map[cid]["today_total"] += 1
                class_stat_map[cid]["today_absent"] += 1
            if sub_id:
                if sub_id not in class_stat_map[cid]["subjects"]:
                    class_stat_map[cid]["subjects"][sub_id] = {"total": 0, "attended": 0, "od": 0}
                class_stat_map[cid]["subjects"][sub_id]["total"] += 1
        elif st_code in ("OD", "ONDUTY", "ON DUTY"):
            class_stat_map[cid]["total"] += 1
            class_stat_map[cid]["on_duty"] += 1
            if is_today:
                class_stat_map[cid]["today_total"] += 1
                class_stat_map[cid]["today_od"] += 1
            if sub_id:
                if sub_id not in class_stat_map[cid]["subjects"]:
                    class_stat_map[cid]["subjects"][sub_id] = {"total": 0, "attended": 0, "od": 0}
                class_stat_map[cid]["subjects"][sub_id]["total"] += 1
                class_stat_map[cid]["subjects"][sub_id]["od"] += 1

    class_stats = []
    for cid, c_info in class_info_map.items():
        st = class_stat_map.get(cid, {
            "total": 0, "attended": 0, "absent": 0, "on_duty": 0,
            "today_total": 0, "today_present": 0, "today_absent": 0, "today_od": 0,
            "subjects": {}
        })
        effective_att = st["attended"] + st["on_duty"]
        pct = round((effective_att / st["total"]) * 100, 1) if st["total"] else 0.0
        
        t_pres = st["today_present"]
        t_abs = st["today_absent"]
        t_od = st["today_od"]
        t_eff = t_pres + t_abs + t_od
        today_pct = round(((t_pres + t_od) / t_eff) * 100, 1) if t_eff else 0.0
        
        students_count = len([s for s in active_students if _classes_match(s.get("ClassID", ""), cid)])

        # Batch & Academic mapping
        raw_yr = str(c_info.get("Year", "")).strip()
        sec = str(c_info.get("Section", "")).strip().upper() or "A"
        
        # Determine Batch and Year details
        if raw_yr in ("27", "2027", "4"):
            batch_label = "Batch 2027"
            year_name = "IV Year (4th Year)"
            batch_sort = 2027
        elif raw_yr in ("28", "2028", "3"):
            batch_label = "Batch 2028"
            year_name = "III Year (3rd Year)"
            batch_sort = 2028
        elif raw_yr in ("29", "2029", "2"):
            batch_label = "Batch 2029"
            year_name = "II Year (2nd Year)"
            batch_sort = 2029
        else:
            batch_label = f"Batch {raw_yr}"
            year_name = f"Year {raw_yr}"
            batch_sort = 9999

        # Subject breakdown for this class/section
        sub_list = []
        for s_id, s_data in st["subjects"].items():
            s_pct = round((s_data["attended"] / s_data["total"]) * 100, 1) if s_data["total"] else 0.0
            sub_list.append({
                "subject_id": s_id,
                "subject_name": subject_map.get(s_id, s_id),
                "total": s_data["total"],
                "attended": s_data["attended"],
                "percentage": s_pct,
            })
        sub_list.sort(key=lambda x: x["percentage"], reverse=True)

        class_stats.append({
            "class_id": cid,
            "class_name": c_info.get("ClassName", cid),
            "year": raw_yr,
            "batch_label": batch_label,
            "academic_year": year_name,
            "batch_sort": batch_sort,
            "section": sec,
            "section_title": f"{batch_label} · Section {sec}",
            "semester": str(c_info.get("Semester", "")).strip(),
            "student_count": students_count,
            "total": st["total"],
            "attended": st["attended"],
            "absent": st["absent"],
            "on_duty": st["on_duty"],
            "percentage": pct,
            "today_total": st["today_total"],
            "today_present": t_pres,
            "today_attended": t_pres,
            "today_absent": t_abs,
            "today_od": t_od,
            "today_percentage": today_pct,
            "defaulters_count": class_defaulter_count.get(cid, 0),
            "subject_breakdown": sub_list,
        })
    
    # Sort class stats by batch (2027, 2028, 2029) then section (A, B)
    class_stats.sort(key=lambda x: (x["batch_sort"], x["section"]))

    # Section Summaries: direct institutional section breakdown
    section_summaries = []
    for cs in class_stats:
        section_summaries.append({
            "class_id": cs["class_id"],
            "class_name": cs["class_name"],
            "section": cs["section"],
            "batch_label": cs["batch_label"],
            "section_title": cs["section_title"],
            "student_count": cs["student_count"],
            "percentage": cs["percentage"],
            "today_total": cs["today_total"],
            "today_present": cs["today_present"],
            "today_absent": cs["today_absent"],
            "today_od": cs["today_od"],
            "today_percentage": cs["today_percentage"],
            "defaulters_count": cs["defaulters_count"],
        })

    year_summaries = []

    hour_stats = []
    for h in ALL_HOURS:
        h_logs = [r for r in valid_logs if str(r.get("Hour", "")).strip().upper() == h]
        h_tot = len(h_logs)
        h_att = len([r for r in h_logs if r.get("Status", "") == "P"])
        h_pct = round((h_att / h_tot) * 100, 1) if h_tot else 0.0
        hour_stats.append({
            "hour": h,
            "label": HOUR_LABELS.get(h, h),
            "total": h_tot,
            "attended": h_att,
            "percentage": h_pct,
        })

    date_map = {}
    for r in valid_logs:
        d = str(r.get("Date", "")).strip()
        if not d:
            continue
        if d not in date_map:
            date_map[d] = {"total": 0, "attended": 0}
        date_map[d]["total"] += 1
        if r.get("Status", "") == "P":
            date_map[d]["attended"] += 1

    def _parse_sort_key(d_str):
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(d_str, fmt)
            except ValueError:
                pass
        return datetime.min

    sorted_dates = sorted(date_map.keys(), key=_parse_sort_key)
    trend = []
    for d in sorted_dates[-14:]:
        t_data = date_map[d]
        pct = round((t_data["attended"] / t_data["total"]) * 100, 1) if t_data["total"] else 0.0
        trend.append({
            "date": d,
            "total": t_data["total"],
            "attended": t_data["attended"],
            "percentage": pct,
        })

    session_groups = {}
    for r in reversed(logs):
        key = (
            str(r.get("Date", "")).strip(),
            str(r.get("ClassID", "")).strip(),
            str(r.get("Hour", "")).strip().upper(),
            str(r.get("SubjectID", "")).strip(),
            str(r.get("FacultyID", "")).strip(),
        )
        if key not in session_groups:
            session_groups[key] = {
                "date": key[0],
                "class_id": key[1],
                "class_name": class_map.get(key[1], key[1]),
                "hour": key[2],
                "subject_id": key[3],
                "faculty_id": key[4],
                "present": 0,
                "absent": 0,
                "timestamp": str(r.get("Timestamp", "")),
            }
        if r.get("Status", "") == "P":
            session_groups[key]["present"] += 1
        elif r.get("Status", "") == "A":
            session_groups[key]["absent"] += 1
        if len(session_groups) >= 8:
            break

    recent_activity = list(session_groups.values())

    return {
        "total_students": len(active_students),
        "total_classes": len(active_classes),
        "total_faculty": len(faculty_users),
        "total_subjects": len(active_subjects),
        "total_records": total_records,
        "overall_percentage": overall_percentage,
        "total_hours": total_hours,
        "attended_hours": attended_hours,
        "today": {
            "date": today_str,
            "total": today_total,
            "present": today_present,
            "attended": today_present,
            "absent": today_absent,
            "on_duty": today_od,
            "percentage": today_percentage,
        },
        "status_distribution": status_distribution,
        "class_stats": class_stats,
        "section_summaries": section_summaries,
        "year_summaries": year_summaries,
        "hour_stats": hour_stats,
        "trend": trend,
        "defaulters": defaulters,
        "defaulters_count": len(defaulters),
        "recent_activity": recent_activity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Background Cache Pre-warming
# ─────────────────────────────────────────────────────────────────────────────
def warm_up_cache():
    """Fetch essential sheets in background so the first user request is instant."""
    try:
        get_all_users()
        get_all_classes()
        _get_raw_subjects()
        _get_raw_students()
        _get_raw_attendance_log()
        print("[Cache] AttendTrax sheets cache successfully pre-warmed!")
    except Exception as e:
        print(f"[Cache] Background cache warming warning: {e}")
