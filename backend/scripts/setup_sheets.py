# =============================================================================
# setup_sheets.py  — AttendTrax Google Sheets Initializer
#
# HOW IT WORKS (service accounts can't own Drive files, so we split into 2 steps):
#
#   STEP A — YOU do (in Google Drive, takes ~3 minutes):
#     1. Create 9 blank Google Spreadsheets in your Drive folder
#        (5 master sheets + 1 per class = 4 classes = 9 total)
#     2. Share each one with your service account email (Editor)
#     3. Paste all their Spreadsheet IDs into the section below
#
#   STEP B — This script does automatically:
#     • Writes correct headers + formatting to all master sheets
#     • Builds monthly tabs (Sep-2026, Oct-2026, Nov-2026) in each class sheet
#     • Writes the header rows, sample students, COUNTIF formulas
#     • Prints all IDs to copy into your .env
#
# Run:
#   cd backend
#   venv\Scripts\activate
#   python setup_sheets.py
# =============================================================================

import json, os, sys, time

# Windows: force UTF-8 so emoji prints correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread
from gspread.exceptions import APIError

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =============================================================================
# ██████████████████  CONFIGURE THIS SECTION  █████████████████████████████████
# =============================================================================

# ── Step A: Create these spreadsheets manually in Google Drive,
#    share each with your service account email (Editor),
#    then paste their IDs below (from the URL: /spreadsheets/d/<ID>/edit)

SHEET_IDS = {
    # Master sheets (5 total)
    "Users":           "1j9IL5xhQaiA6uMWEWsJQcK6XsWN8WH-FrdxwP5iSNBo",
    "Classes":         "1aqgUaZPSDh_WAtjQTo00SehlYwPNFDIRZse2CYWHoiE",
    "Students":        "1HCpSRIVN5uEf73JBRQIQU0ZA-jTrqK8lgzOa2vcUySs",
    "Subjects":        "1NlQ0YdgHAVOYnQc04BwSpStGHM_oHhLq4D31_lp-NTY",
    "Attendance_Log":  "1asNPUg3-PoPLI_TlJisl2T0EevB7BLJLRfoq9ENsIbU",

    # One per class  (match your class_id values below)
    "CSE4A":  "1BKKiXO1LDadRIOBg6o16t72tpFabOMEq85-rVlXIJcQ",
    "CSE27A": "1BKKiXO1LDadRIOBg6o16t72tpFabOMEq85-rVlXIJcQ",
    "CSE3A":  "1ZE6IOG4AzT1xir_8YYWzHIJL8G2l-Kq3fx76aQ0c3MU",
    "CSE3B":  "11SpxEbxb_QG4_wqKsiYNk9fgr7qVQxn48VlA0Nz4dTQ",
    "CSE2A":  "1PE_5-0M3NA_Uf8L4k6pz4hrg2vGoDcNfc6d2ORALfcc",
    "CSE2B":  "1njW1gjuG1gQnD4gElGcRlbfZLGazx6xXm8adtZZzNpA",
    "CSE28A": "1ZE6IOG4AzT1xir_8YYWzHIJL8G2l-Kq3fx76aQ0c3MU",
    "CSE28B": "11SpxEbxb_QG4_wqKsiYNk9fgr7qVQxn48VlA0Nz4dTQ",
    "CSE29A": "1PE_5-0M3NA_Uf8L4k6pz4hrg2vGoDcNfc6d2ORALfcc",
    "CSE29B": "1njW1gjuG1gQnD4gElGcRlbfZLGazx6xXm8adtZZzNpA",
}


# ── Class definitions (must match keys above) ─────────────────────────────────
CLASSES = [
    {"class_id": "CSE4A", "class_name": "CSE IV Year A",  "year": "4", "section": "A", "semester": "7"},
    {"class_id": "CSE3A", "class_name": "CSE III Year A", "year": "3", "section": "A", "semester": "5"},
    {"class_id": "CSE3B", "class_name": "CSE III Year B", "year": "3", "section": "B", "semester": "5"},
    {"class_id": "CSE2A", "class_name": "CSE II Year A",  "year": "2", "section": "A", "semester": "3"},
    {"class_id": "CSE2B", "class_name": "CSE II Year B",  "year": "2", "section": "B", "semester": "3"},
]

# ── Semester months to create in each class sheet ────────────────────────────
MONTHS = ["Sep-2026", "Oct-2026", "Nov-2026", "Dec-2026"]

# ── Sample students per class (for template rows only) ────────────────────────
# The real students will be added via the Admin dashboard or directly in Students sheet.
SAMPLE_STUDENTS = [
    ["23CS001", "Student One"],
    ["23CS002", "Student Two"],
    ["23CS003", "Student Three"],
]

# ── Hour labels ───────────────────────────────────────────────────────────────
HOUR_LABELS = ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"]
SAMPLE_DATES = ["29-09-2026", "30-09-2026"]   # 2 demo dates shown in template

# =============================================================================
# END CONFIGURE SECTION
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def col_letter(n: int) -> str:
    """Convert 1-based column index to A1-notation letter(s)."""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _rate(fn, *args, **kwargs):
    """Retry on rate-limit errors and connection drops."""
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            # Catch API quota errors and lower-level connection drops
            if any(k in err_str for k in ["429", "RESOURCE_EXHAUSTED", "Connection aborted", "RemoteDisconnected", "Timeout"]):
                wait = 20 * (attempt + 1)
                print(f"   [network/rate limit] waiting {wait}s ... (Error: {type(e).__name__})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Failed after retries: {fn}")


def auth() -> gspread.Client:
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not creds_json:
        sys.exit("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON not set in .env")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    return gspread.authorize(creds)


def open_sheet(client: gspread.Client, sheet_id: str, label: str) -> gspread.Spreadsheet:
    if not sheet_id.strip():
        sys.exit(f"\nERROR: ID for '{label}' is blank in SHEET_IDS. Paste the spreadsheet ID and re-run.")
    try:
        return client.open_by_key(sheet_id.strip())
    except Exception as e:
        sys.exit(f"\nERROR opening '{label}' ({sheet_id}): {e}\n"
                 f"Make sure the sheet exists and is shared with the service account (Editor).")


# ─────────────────────────────────────────────────────────────────────────────
# Formatting constants
# ─────────────────────────────────────────────────────────────────────────────
HEADER_BG   = {"red": 0.118, "green": 0.231, "blue": 0.537}   # dark blue
HEADER_TEXT = {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
DATE_BG     = {"red": 0.216, "green": 0.400, "blue": 0.698}   # medium blue
HOUR_BG     = {"red": 0.827, "green": 0.863, "blue": 0.949}   # light blue
TITLE_BG    = {"red": 0.063, "green": 0.353, "blue": 0.290}   # dark green
GREY_BG     = {"red": 0.949, "green": 0.953, "blue": 0.961}

CENTER = {"horizontalAlignment": "CENTER"}
BOLD   = {"textFormat": {"bold": True}}
WHITE_TEXT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}


# ─────────────────────────────────────────────────────────────────────────────
# MASTER SHEETS
# ─────────────────────────────────────────────────────────────────────────────
MASTER_SPECS = [
    {
        "key": "Users",
        "tab": "Users",
        "headers": ["UserID", "Name", "Username", "PasswordHash", "Role", "ClassID"],
        "widths":  [100, 180, 140, 340, 90, 100],
        "sample": [
            ["ADM001", "Admin", "admin", "<generate bcrypt hash via passlib>", "ADMIN", ""],
            ["FAC001", "Faculty Name", "faculty01", "<bcrypt hash>", "FACULTY", ""],
            ["23CS001", "Student Name", "23CS001", "<bcrypt hash of reg number>", "STUDENT", "CSE3A"],
        ],
    },
    {
        "key": "Classes",
        "tab": "Classes",
        "headers": ["ClassID", "ClassName", "Year", "Section", "Semester", "Status", "SpreadsheetID"],
        "widths":  [90, 200, 60, 70, 80, 80, 380],
        "sample": [],   # filled by script at the end
    },
    {
        "key": "Students",
        "tab": "Students",
        "headers": ["RegNo", "Name", "ClassID", "ClassName", "Status"],
        "widths":  [110, 200, 90, 200, 80],
        "sample": [
            ["23CS001", "Student One",   "CSE3A", "CSE III Year A", "ACTIVE"],
            ["23CS002", "Student Two",   "CSE3A", "CSE III Year A", "ACTIVE"],
            ["23CS101", "Student Three", "CSE3B", "CSE III Year B", "ACTIVE"],
        ],
    },
    {
        "key": "Subjects",
        "tab": "Subjects",
        "headers": ["SubjectID", "ClassID", "SubjectName", "FacultyID", "Status"],
        "widths":  [110, 90, 260, 100, 80],
        "sample": [
            ["CS301", "CSE3A", "Data Structures & Algorithms",    "FAC001", "ACTIVE"],
            ["CS302", "CSE3A", "Database Management Systems",     "FAC001", "ACTIVE"],
            ["CS303", "CSE3A", "Operating Systems",               "FAC001", "ACTIVE"],
            ["CS304", "CSE3A", "Computer Networks",               "FAC001", "ACTIVE"],
        ],
    },
    {
        "key": "Attendance_Log",
        "tab": "Attendance_Log",
        "headers": ["ID", "Date", "ClassID", "Hour", "SubjectID", "RegNo", "Status", "FacultyID", "Timestamp"],
        "widths":  [50, 100, 90, 55, 110, 110, 65, 100, 175],
        "sample": [],
    },
]


def setup_master_sheet(client: gspread.Client, spec: dict) -> None:
    key    = spec["key"]
    tab    = spec["tab"]
    ss     = open_sheet(client, SHEET_IDS[key], key)
    headers = spec["headers"]
    n       = len(headers)

    print(f"  [{key}] Writing headers ...")
    ws = ss.sheet1
    _rate(ws.update_title, tab)
    _rate(ws.update, "A1", [headers])

    # Header formatting
    end = col_letter(n)
    _rate(ws.format, f"A1:{end}1", {
        "backgroundColor": HEADER_BG,
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })
    _rate(ws.freeze, rows=1)

    # Column widths via batch_update
    width_requests = []
    for i, w in enumerate(spec.get("widths", [])):
        width_requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })
    if width_requests:
        _rate(ss.batch_update, {"requests": width_requests})

    # Sample rows
    if spec.get("sample"):
        _rate(ws.update, "A2", spec["sample"])
        # Light alternating background
        for row_i, _ in enumerate(spec["sample"]):
            if row_i % 2 == 0:
                _rate(ws.format, f"A{2 + row_i}:{end}{2 + row_i}",
                      {"backgroundColor": GREY_BG})

    print(f"  [{key}] Done.")
    time.sleep(1.5)


# ─────────────────────────────────────────────────────────────────────────────
# CLASS ATTENDANCE SHEETS
# ─────────────────────────────────────────────────────────────────────────────
def setup_class_sheet(client: gspread.Client, cls: dict, months: list) -> None:
    class_id   = cls["class_id"]
    class_name = cls["class_name"]
    ss         = open_sheet(client, SHEET_IDS[class_id], f"Class:{class_id}")
    print(f"  [{class_id}] Building {len(months)} monthly sheets ...")

    existing_tabs = [ws.title for ws in ss.worksheets()]

    for idx, month in enumerate(months):
        if month in existing_tabs:
            print(f"    {month} already exists – skipping.")
            continue

        print(f"    Creating {month} ...")
        if idx == 0 and "Sheet1" in existing_tabs:
            ws = ss.sheet1
            _rate(ws.update_title, month)
        else:
            ws = _rate(ss.add_worksheet, title=month, rows=300, cols=300)

        _build_monthly_tab(ss, ws, class_id, class_name, month)
        time.sleep(2)

    print(f"  [{class_id}] Done.")


def _build_monthly_tab(ss, ws, class_id: str, class_name: str, month_label: str) -> None:
    """
    Layout:
      Row 1 : TITLE banner (merged full width)
      Row 2 : "Reg No" | "Student Name" | <date merged 8 cols> | <date> | ...
      Row 3 : ""        | ""             | H1 | H2 | H3 | H4 | H5 | H6 | H7 | H8 | repeat
      Row 4+: student data
      Row N : Total Present  | COUNTIF per col
      Row N+1: Total Absent  | COUNTIF per col
      Row N+2: Total Hours   | COUNTIF per col
    """
    nd  = len(SAMPLE_DATES)
    tc  = 2 + nd * 8          # total data columns
    ec  = col_letter(tc)      # last data column letter

    STUDENT_START = 4          # student data begins at row 4
    num_students  = len(SAMPLE_STUDENTS)
    student_end   = STUDENT_START + num_students - 1
    summary_row   = student_end + 2

    # ── Row 1: Title banner ───────────────────────────────────────────────────
    title = f"ATTENDANCE REGISTER  |  {class_name.upper()}  |  {month_label.upper()}"
    _rate(ws.update, "A1", [[title]])

    # ── Row 2: Reg No / Student Name / date super-headers ─────────────────────
    row2 = ["Reg No", "Student Name"]
    for d in SAMPLE_DATES:
        row2.append(d)
        row2.extend([""] * 7)
    _rate(ws.update, "A2", [row2])

    # ── Row 3: hour sub-headers ───────────────────────────────────────────────
    row3 = ["", ""]
    for _ in SAMPLE_DATES:
        row3.extend(HOUR_LABELS)
    _rate(ws.update, "A3", [row3])

    # ── Rows 4+: sample students ──────────────────────────────────────────────
    for si, student in enumerate(SAMPLE_STUDENTS):
        row_vals = list(student)
        for _ in SAMPLE_DATES:
            row_vals.extend(["P"] * 8)
        _rate(ws.update, f"A{STUDENT_START + si}", [row_vals])
        time.sleep(0.2)

    # ── Summary rows with COUNTIF ─────────────────────────────────────────────
    _rate(ws.update, f"A{summary_row}",     [["", "Total Present"]])
    _rate(ws.update, f"A{summary_row + 1}", [["", "Total Absent"]])
    _rate(ws.update, f"A{summary_row + 2}", [["", "Total Hours"]])

    for c_off in range(nd * 8):
        cl = col_letter(3 + c_off)
        _rate(ws.update_cell, summary_row,     3 + c_off, f'=COUNTIF({cl}{STUDENT_START}:{cl}{student_end},"P")')
        _rate(ws.update_cell, summary_row + 1, 3 + c_off, f'=COUNTIF({cl}{STUDENT_START}:{cl}{student_end},"A")')
        _rate(ws.update_cell, summary_row + 2, 3 + c_off, f'=COUNTIF({cl}{STUDENT_START}:{cl}{student_end},"<>-")')
        time.sleep(0.15)

    # ── Formatting ────────────────────────────────────────────────────────────
    # Title row
    _rate(ws.format, f"A1:{ec}1", {
        "backgroundColor": TITLE_BG,
        "textFormat": {"bold": True, "fontSize": 12,
                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    })
    # Row 2 fixed cols
    _rate(ws.format, "A2:B2", {
        "backgroundColor": HEADER_BG, **WHITE_TEXT, **CENTER,
    })
    # Date super-headers (row 2)
    for di in range(nd):
        sc = col_letter(3 + di * 8)
        _ec = col_letter(3 + di * 8 + 7)
        _rate(ws.format, f"{sc}2:{_ec}2", {
            "backgroundColor": DATE_BG, **WHITE_TEXT, **CENTER,
        })
    # Hour sub-headers (row 3)
    _rate(ws.format, f"A3:B3", {"backgroundColor": HEADER_BG, **WHITE_TEXT, **CENTER})
    _rate(ws.format, f"C3:{ec}3", {"backgroundColor": HOUR_BG, **BOLD, **CENTER})
    # Student data columns
    _rate(ws.format, f"A4:B{student_end}", {"backgroundColor": GREY_BG})
    # Summary label styling
    _rate(ws.format, f"B{summary_row}:B{summary_row + 2}", {
        "backgroundColor": {"red": 1, "green": 0.95, "blue": 0.8},
        "textFormat": {"bold": True},
    })

    # ── Merge cells ──────────────────────────────────────────────────────────
    merge_requests = []
    # Title row (row 1)
    merge_requests.append({"mergeCells": {
        "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": tc},
        "mergeType": "MERGE_ALL",
    }})
    # Date super-headers (row 2)
    for di in range(nd):
        sc0 = 2 + di * 8
        merge_requests.append({"mergeCells": {
            "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": sc0, "endColumnIndex": sc0 + 8},
            "mergeType": "MERGE_ALL",
        }})
    _rate(ss.batch_update, {"requests": merge_requests})
    time.sleep(0.5)

    # ── Freeze + column widths ────────────────────────────────────────────────
    _rate(ws.freeze, rows=3, cols=2)

    dim_requests = [
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 100}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 185}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": tc},
            "properties": {"pixelSize": 36}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 38}, "fields": "pixelSize",
        }},
    ]
    _rate(ss.batch_update, {"requests": dim_requests})


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_ids() -> bool:
    """Print which IDs are missing and return False if any are blank."""
    missing = [k for k, v in SHEET_IDS.items() if not v.strip()]
    if missing:
        print("\n" + "=" * 60)
        print("  ACTION REQUIRED — Paste Spreadsheet IDs")
        print("=" * 60)
        print("\nThe following sheets have no ID set in SHEET_IDS:\n")
        for k in missing:
            print(f"  [ ] {k}")
        print("""
Steps:
  1. Open Google Drive → your attendance folder
  2. For each name above:
       a. Create a blank Google Spreadsheet with that name
       b. Share it with your service account email (Editor)
       c. Copy its ID from the URL: /spreadsheets/d/<ID>/edit
       d. Paste it into SHEET_IDS["{name}"] in setup_sheets.py
  3. Re-run:  python setup_sheets.py
""")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  AttendTrax — Google Sheets Setup Script")
    print("=" * 60)

    if not validate_ids():
        sys.exit(1)

    client = auth()
    print("\n✅ Authenticated as service account.\n")

    # ── 1. Master sheets ──────────────────────────────────────────────────────
    print("── Setting up master sheets ──")
    for spec in MASTER_SPECS:
        setup_master_sheet(client, spec)

    # ── 2. Class attendance sheets ────────────────────────────────────────────
    print("\n── Setting up class attendance sheets ──")
    for cls in CLASSES:
        setup_class_sheet(client, cls, MONTHS)
        time.sleep(2)

    # ── 3. Populate Classes master with class info + spreadsheet IDs ──────────
    print("\n── Writing class list into Classes sheet ──")
    classes_ss = open_sheet(client, SHEET_IDS["Classes"], "Classes")
    classes_ws = classes_ss.worksheet("Classes")
    rows = []
    for cls in CLASSES:
        rows.append([
            cls["class_id"],
            cls["class_name"],
            cls.get("year", ""),
            cls.get("section", ""),
            cls.get("semester", ""),
            "ACTIVE",
            SHEET_IDS.get(cls["class_id"], ""),
        ])
    _rate(classes_ws.update, "A2", rows)
    print("  Classes sheet populated. ✅")

    # ── 4. Print .env values ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DONE — Add these to your .env (or Render env vars)")
    print("=" * 60)
    print(f"\nUSERS_SHEET_ID={SHEET_IDS['Users']}")
    print(f"CLASSES_SHEET_ID={SHEET_IDS['Classes']}")
    print(f"STUDENTS_SHEET_ID={SHEET_IDS['Students']}")
    print(f"SUBJECTS_SHEET_ID={SHEET_IDS['Subjects']}")
    print(f"ATTENDANCE_LOG_SHEET_ID={SHEET_IDS['Attendance_Log']}")
    print(f"SPREADSHEET_FOLDER_ID={os.getenv('SPREADSHEET_FOLDER_ID','')}")

    print("\n── Next: generate your admin bcrypt hash ──")
    print("python -c \"from passlib.context import CryptContext; "
          "ctx=CryptContext(schemes=['bcrypt']); print(ctx.hash('YOUR_PASSWORD'))\"")
    print("\nThen paste it into row 2 of the Users sheet (PasswordHash column).\n")


if __name__ == "__main__":
    main()
