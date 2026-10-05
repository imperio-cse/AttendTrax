# =============================================================================
# setup_daily_registers.py
# Formats all per-class Google Sheets into daily manual-attendance style registers:
# - Col A: Reg No
# - Col B: Student Name
# - Col C..Z: Dates (01-10-2026, 02-10-2026, ...)
# - Right Summary Columns: Total Present, Total Absent, Total OD, Overall %
# - Bottom Summary Rows: Total Present, Total Absent, Total OD, Daily %
# =============================================================================
import calendar
from datetime import date, datetime
import json
import os
import sys
import time
from typing import Dict, List

# Ensure UTF-8 stdout encoding for Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import gspread
from google.oauth2.service_account import Credentials
from config import get_settings


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Spreadsheet ID mapping
SHEET_IDS = {
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

CLASS_TARGETS = [
    {"class_ids": ["CSE27A", "CSE4A"], "name": "CSE 4A (IV Year A)", "sheet_id": "1BKKiXO1LDadRIOBg6o16t72tpFabOMEq85-rVlXIJcQ"},
    {"class_ids": ["CSE28A", "CSE3A"], "name": "CSC 3A (III Year A)", "sheet_id": "1ZE6IOG4AzT1xir_8YYWzHIJL8G2l-Kq3fx76aQ0c3MU"},
    {"class_ids": ["CSE28B", "CSE3B"], "name": "SCC 3B (III Year B)", "sheet_id": "11SpxEbxb_QG4_wqKsiYNk9fgr7qVQxn48VlA0Nz4dTQ"},
    {"class_ids": ["CSE29A", "CSE2A"], "name": "CSE 2A (II Year A)",  "sheet_id": "1PE_5-0M3NA_Uf8L4k6pz4hrg2vGoDcNfc6d2ORALfcc"},
    {"class_ids": ["CSE29B", "CSE2B"], "name": "CSE 2B (II Year B)",  "sheet_id": "1njW1gjuG1gQnD4gElGcRlbfZLGazx6xXm8adtZZzNpA"},
]

def col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result

def get_client() -> gspread.Client:
    cfg = get_settings()
    creds_dict = json.loads(cfg.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def _rate(fn, *args, **kwargs):
    """Retries operation on connection errors or rate limits."""
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if any(k in err_str for k in ["429", "RESOURCE_EXHAUSTED", "Connection aborted", "RemoteDisconnected", "Timeout", "wsarecv", "forcibly closed"]):
                wait = 4 * (attempt + 1)
                print(f"   [network retry] waiting {wait}s ({type(e).__name__})...")
                time.sleep(wait)
            else:
                raise
    return fn(*args, **kwargs)


def format_class_daily_register(client: gspread.Client, target: dict, year: int = 2026, month: int = 10):
    sheet_id = target["sheet_id"]
    class_name = target["name"]
    target_cids = target["class_ids"]

    month_name = calendar.month_name[month]
    month_abbr = calendar.month_abbr[month]
    month_label = f"{month_abbr}-{year}"
    num_days = calendar.monthrange(year, month)[1]

    print(f"\n[{class_name}] Setting up daily register for {month_label} ({num_days} days)...")
    ss = client.open_by_key(sheet_id)

    # 1. Fetch real students for these class IDs
    import sheets
    all_students = sheets._get_raw_students()
    students = [
        s for s in all_students
        if str(s.get("ClassID", "")).strip() in target_cids
        and str(s.get("Status", "")).upper() == "ACTIVE"
    ]
    # Sort students by RegNo
    students.sort(key=lambda s: str(s.get("RegNo", "")))
    print(f"  Found {len(students)} active students in database.")

    # 2. Fetch attendance logs for existing dates
    all_logs = sheets._get_raw_attendance_log()
    class_logs = [
        r for r in all_logs
        if str(r.get("ClassID", "")).strip() in target_cids
    ]
    # (reg_no, date_str) -> status
    log_lookup = {}
    for r in class_logs:
        rn = str(r.get("RegNo", "")).strip()
        d = str(r.get("Date", "")).strip()
        st = str(r.get("Status", "")).strip().upper()
        if rn and d and st:
            log_lookup[(rn, d)] = st

    # 3. Create or select Worksheet
    ws_titles = [w.title for w in ss.worksheets()]
    if month_label in ws_titles:
        ws = ss.worksheet(month_label)
        ws.clear()
    elif "Sheet1" in ws_titles and len(ws_titles) == 1:
        ws = ss.sheet1
        ws.update_title(month_label)
        ws.clear()
    else:
        ws = ss.add_worksheet(title=month_label, rows=120, cols=50)

    # 4. Build Grid
    # Header Row 1: Title Banner
    # Header Row 2: Reg No | Student Name | 01-10-2026 | 02-10-2026 | ... | Total Present | Total Absent | Total OD | Attendance %
    date_cols = []
    for d in range(1, num_days + 1):
        d_str = f"{d:02d}-{month:02d}-{year}"
        date_cols.append(d_str)

    num_dates = len(date_cols)
    total_cols = 2 + num_dates + 4  # RegNo, Name, Dates, 4 Summary cols

    row1 = [f"DAILY ATTENDANCE REGISTER  |  {class_name.upper()}  |  {month_name.upper()} {year}"] + [""] * (total_cols - 1)
    row2 = ["Reg No", "Student Name"] + date_cols + ["Total Present", "Total Absent", "Total OD", "Attendance %"]

    all_rows = [row1, row2]

    start_student_row = 3
    num_students = len(students)

    for i, s in enumerate(students):
        rn = str(s.get("RegNo", "")).strip()
        sname = str(s.get("Name", "")).strip()
        curr_row_num = start_student_row + i

        # Populate student days
        day_statuses = []
        for d_str in date_cols:
            st = log_lookup.get((rn, d_str), "")
            # Check if holiday (e.g. 02-10 Gandhi Jayanti or Sunday)
            dt_obj = datetime.strptime(d_str, "%d-%m-%Y")
            if not st:
                if dt_obj.weekday() == 6:  # Sunday
                    st = "Holiday"
                elif d_str == "02-10-2026":  # Gandhi Jayanti
                    st = "Holiday"
                elif d_str == "01-10-2026":  # Current date default
                    st = "P"
                else:
                    st = ""
            day_statuses.append(st)

        first_date_col = col_letter(3)
        last_date_col = col_letter(2 + num_dates)

        f_present = f'=COUNTIF({first_date_col}{curr_row_num}:{last_date_col}{curr_row_num}, "P")'
        f_absent  = f'=COUNTIF({first_date_col}{curr_row_num}:{last_date_col}{curr_row_num}, "A")'
        f_od      = f'=COUNTIF({first_date_col}{curr_row_num}:{last_date_col}{curr_row_num}, "OD")'
        col_pres  = col_letter(2 + num_dates + 1)
        col_abs   = col_letter(2 + num_dates + 2)
        f_pct     = f'=IF(({col_pres}{curr_row_num}+{col_abs}{curr_row_num})>0, ROUND(({col_pres}{curr_row_num}/({col_pres}{curr_row_num}+{col_abs}{curr_row_num}))*100, 1)&"%", "0.0%")'

        student_row = [rn, sname] + day_statuses + [f_present, f_absent, f_od, f_pct]
        all_rows.append(student_row)

    end_student_row = start_student_row + num_students - 1 if num_students else start_student_row

    # Empty spacer row
    all_rows.append([""] * total_cols)

    # Bottom Summary rows
    r_pres_num = end_student_row + 2
    r_abs_num  = end_student_row + 3
    r_od_num   = end_student_row + 4
    r_pct_num  = end_student_row + 5

    r_pres = ["", "Total Present"]
    r_abs  = ["", "Total Absent"]
    r_od   = ["", "Total OD"]
    r_pct  = ["", "Daily %"]

    for di in range(num_dates):
        cl = col_letter(3 + di)
        r_pres.append(f'=COUNTIF({cl}{start_student_row}:{cl}{end_student_row}, "P")')
        r_abs.append(f'=COUNTIF({cl}{start_student_row}:{cl}{end_student_row}, "A")')
        r_od.append(f'=COUNTIF({cl}{start_student_row}:{cl}{end_student_row}, "OD")')
        r_pct.append(f'=IF((COUNTIF({cl}{start_student_row}:{cl}{end_student_row},"P")+COUNTIF({cl}{start_student_row}:{cl}{end_student_row},"A"))>0, ROUND((COUNTIF({cl}{start_student_row}:{cl}{end_student_row},"P")/(COUNTIF({cl}{start_student_row}:{cl}{end_student_row},"P")+COUNTIF({cl}{start_student_row}:{cl}{end_student_row},"A")))*100, 1)&"%", "-")')

    # Right spacer in summary rows
    r_pres += ["", "", "", ""]
    r_abs  += ["", "", "", ""]
    r_od   += ["", "", "", ""]
    r_pct  += ["", "", "", ""]

    all_rows.append(r_pres)
    all_rows.append(r_abs)
    all_rows.append(r_od)
    all_rows.append(r_pct)

    # 5. Write all data in single batch
    print("  Writing grid data to Google Sheets...")
    end_col_str = col_letter(total_cols)
    _rate(ws.update, values=all_rows, range_name=f"A1:{end_col_str}{len(all_rows)}", value_input_option="USER_ENTERED")

    # 6. Apply Professional Formatting & Styling via single batch_format
    print("  Applying professional visual styles & freeze panes...")
    header_end = col_letter(total_cols)
    last_date_cl = col_letter(2 + num_dates)
    sum_start_cl = col_letter(2 + num_dates + 1)

    formats = [
        # Title row format
        {
            "range": f"A1:{header_end}1",
            "format": {
                "backgroundColor": {"red": 0.118, "green": 0.227, "blue": 0.541},  # #1E3A8A
                "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
            }
        },
        # Header row 2 format
        {
            "range": f"A2:B2",
            "format": {
                "backgroundColor": {"red": 0.231, "green": 0.510, "blue": 0.965},  # #3B82F6
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
            }
        },
        {
            "range": f"C2:{last_date_cl}2",
            "format": {
                "backgroundColor": {"red": 0.231, "green": 0.510, "blue": 0.965},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
            }
        },
        {
            "range": f"{sum_start_cl}2:{header_end}2",
            "format": {
                "backgroundColor": {"red": 0.059, "green": 0.463, "blue": 0.361},  # #0F766E
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
            }
        },
        # Summary rows format
        {
            "range": f"B{r_pres_num}:B{r_pct_num}",
            "format": {
                "backgroundColor": {"red": 0.949, "green": 0.953, "blue": 0.961},
                "textFormat": {"bold": True},
            }
        },
        {
            "range": f"C{r_pres_num}:{last_date_cl}{r_pct_num}",
            "format": {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }
        },
        # Student rows alignment
        {
            "range": f"A{start_student_row}:A{end_student_row}",
            "format": {"horizontalAlignment": "CENTER"}
        },
        {
            "range": f"C{start_student_row}:{header_end}{end_student_row}",
            "format": {"horizontalAlignment": "CENTER"}
        },
    ]

    _rate(ws.batch_format, formats)

    # Freeze top 2 header rows
    _rate(ws.freeze, rows=2)



    # Column widths
    col_widths = [
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 120}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 180}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 2 + num_dates},
            "properties": {"pixelSize": 85}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 2 + num_dates, "endIndex": total_cols},
            "properties": {"pixelSize": 105}, "fields": "pixelSize",
        }},
    ]
    ss.batch_update({"requests": col_widths})

    print(f"  [{class_name}] Daily Register setup complete. ✅")
    time.sleep(1.5)


def update_master_classes_sheet_links(client: gspread.Client):
    print("\nLinking spreadsheet IDs in master Classes sheet...")
    cfg = get_settings()
    ws = client.open_by_key(cfg.CLASSES_SHEET_ID).worksheet("Classes")
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):
        cid = str(row.get("ClassID", "")).strip()
        if cid in SHEET_IDS and SHEET_IDS[cid]:
            ws.update_cell(i, 7, SHEET_IDS[cid])
    print("Master Classes sheet updated with Spreadsheet IDs. ✅")


def main():
    print("=" * 60)
    print("  ATTENDTRAX — DAILY CLASS ATTENDANCE REGISTER BUILDER")
    print("=" * 60)

    client = get_client()

    # 1. Update master classes links
    update_master_classes_sheet_links(client)

    # 2. Format all 4 class spreadsheets for October 2026
    for target in CLASS_TARGETS:
        format_class_daily_register(client, target, year=2026, month=10)

    print("\n" + "=" * 60)
    print("🎉 ALL 4 CLASS REGISTERS SUCCESSFULLY BUILT & POPULATED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
