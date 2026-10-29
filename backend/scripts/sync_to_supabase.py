# =============================================================================
# sync_to_supabase.py – Fast Bulk Migration from Local SQLite to Supabase
# =============================================================================
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, date

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncpg

SUPABASE_URL = "postgresql://postgres:bY69u08s7eu0aKZo@db.ubkvrgwwelrrwqtlmqcq.supabase.co:5432/postgres"
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attendtrax.db")

# Only need to sync remaining tables: hostel_gate_passes & audit_logs
REMAINING_TABLES = [
    "hostel_gate_passes",
    "audit_logs",
]


async def migrate_remaining():
    s_conn = sqlite3.connect(SQLITE_PATH)
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()

    p_conn = await asyncpg.connect(SUPABASE_URL, timeout=30)
    print("Connected to Supabase. Syncing remaining tables...")

    for tbl in REMAINING_TABLES:
        rows = s_cur.execute(f"SELECT * FROM {tbl}").fetchall()
        if not rows:
            print(f"  • {tbl}: 0 rows (skipping)")
            continue

        cols = [col[0] for col in s_cur.description]
        col_names = ", ".join(cols)
        val_placeholders = ", ".join([f"${i+1}" for i in range(len(cols))])
        insert_sql = f"INSERT INTO {tbl} ({col_names}) VALUES ({val_placeholders}) ON CONFLICT DO NOTHING;"

        prepared_rows = []
        for r in rows:
            row_vals = []
            for c in cols:
                val = r[c]
                if c.endswith("_id") and isinstance(val, str):
                    try:
                        val = int(val)
                    except ValueError:
                        val = 4
                elif isinstance(val, int) and c in ("is_active", "has_class_incharge_approval", "has_hod_approval", "has_warden_approval", "security_cleared", "active"):
                    row_vals.append(bool(val))
                elif isinstance(val, str) and ("date" in c or "_at" in c or "valid_" in c):
                    try:
                        if len(val) == 10:
                            row_vals.append(datetime.strptime(val, "%Y-%m-%d").date())
                        else:
                            row_vals.append(datetime.fromisoformat(val.replace("Z", "")))
                    except Exception:
                        row_vals.append(val)
                else:
                    row_vals.append(val)
            prepared_rows.append(tuple(row_vals))

        await p_conn.executemany(insert_sql, prepared_rows)
        print(f"  ✓ {tbl}: {len(rows):,} rows transferred successfully")

        try:
            await p_conn.execute(f"""
                SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), COALESCE(max(id), 1)) FROM {tbl};
            """)
        except Exception:
            pass

    s_conn.close()
    await p_conn.close()
    print("🎉 All remaining tables synchronized with Supabase!")


if __name__ == "__main__":
    asyncio.run(migrate_remaining())
