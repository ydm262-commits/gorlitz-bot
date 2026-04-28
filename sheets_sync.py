"""
sheets_sync.py - סנכרון נתונים מגוגל שיטס לבסיס הנתונים
מושך את גיליון בקרת_מאפייה ומעדכן weekly_orders בכל שבוע חדש
וגם מסנכרן הערות מגיליון סיכום שבועי
"""

import os
import csv
import io
import requests
from typing import List, Dict, Optional
from database import get_database

PRODUCT_COLS = [
    "חלות מתוק",
    "רוגלך שוקולד",
    "רוגלך עלים קקאו",
    "קוקוש קייק",
    "קראנץ' קקאו",
    "פס שוקולד פירורים",
    "פס שמרים קקאו שקית",
    "פס שמרים גבינה",
    "גביניות",
]

SUMMARY_GID = "1529932695"  # טאב "סיכום שבועי"


def fetch_sheet_csv(sheet_id: str, gid: str = "0") -> Optional[str]:
    """מושך את הגיליון כ-CSV מגוגל שיטס ציבורי"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.text
        print(f"Sheet fetch failed: {resp.status_code}")
        return None
    except Exception as e:
        print(f"Sheet fetch error: {e}")
        return None


def parse_orders_from_csv(csv_text: str) -> List[Dict]:
    """
    מנתח CSV של גיליון הזמנות מפורטות.
    מחפש שורה שמתחילה ב'שבוע' ואחריה תאריך ומספרים.
    """
    orders = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    header_row = None
    data_start = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == 'שבוע' and len(row) >= 5:
            header_row = i
            data_start = i + 1
            break

    if header_row is None:
        print("לא נמצאה טבלת הזמנות")
        return []

    for row in rows[data_start:]:
        if not row or not row[0].strip().isdigit():
            break
        try:
            week_num = int(row[0].strip())
            date_str = row[1].strip()  # פורמט DD/MM/YYYY

            parts = date_str.split('/')
            if len(parts) == 3:
                iso_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            else:
                continue

            qtys = {}
            for j, product in enumerate(PRODUCT_COLS):
                try:
                    qty = int(row[j + 2].strip()) if j + 2 < len(row) else 0
                    qtys[product] = qty
                except (ValueError, IndexError):
                    qtys[product] = 0

            if sum(qtys.values()) == 0:
                continue

            orders.append({"week_date": iso_date, "orders": qtys})
        except Exception:
            continue

    return orders


def parse_summary_notes_from_csv(csv_text: str) -> List[Dict]:
    """
    מנתח CSV של גיליון סיכום שבועי.
    קולט תאריך (עמודה B) והערות (עמודה H).
    מבנה: שבוע | תאריך | עלות | הכנסה | פחת | רווח | גדרים | הערות
    """
    notes_list = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # חפש שורת כותרת עם "שבוע" ו"תאריך"
    data_start = None
    notes_col = None
    date_col = None

    for i, row in enumerate(rows):
        row_clean = [c.strip() for c in row]
        if 'שבוע' in row_clean and 'תאריך' in row_clean:
            data_start = i + 1
            date_col = row_clean.index('תאריך')
            # הערות — חפש עמודה בשם "הערות" או השתמש בעמודה 7
            if 'הערות' in row_clean:
                notes_col = row_clean.index('הערות')
            else:
                notes_col = 7  # ברירת מחדל: עמודה H
            break

    if data_start is None:
        print("לא נמצאה כותרת בגיליון סיכום")
        return []

    for row in rows[data_start:]:
        if not row or not row[0].strip().isdigit():
            break
        try:
            date_str = row[date_col].strip() if date_col < len(row) else ''
            note = row[notes_col].strip() if notes_col < len(row) else ''

            if not date_str or not note:
                continue

            # המר DD/MM/YYYY → YYYY-MM-DD
            parts = date_str.split('/')
            if len(parts) == 3:
                iso_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                notes_list.append({"week_date": iso_date, "note": note})
        except Exception:
            continue

    return notes_list


def sync_from_google_sheets() -> Dict:
    """
    מסנכרן הזמנות מפורטות + הערות שבועיות מגוגל שיטס.
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        return {"success": False, "error": "GOOGLE_SHEET_ID לא מוגדר"}

    db = get_database()
    cursor = db.conn.cursor()
    updated = 0
    notes_updated = 0

    # --- שלב 1: הזמנות מפורטות (גיליון ראשי) ---
    csv_orders = fetch_sheet_csv(sheet_id)
    if csv_orders:
        orders = parse_orders_from_csv(csv_orders)
        for week_data in orders:
            date = week_data["week_date"]
            for product, qty in week_data["orders"].items():
                result = cursor.execute("""
                    INSERT OR REPLACE INTO weekly_orders (week_date, product_name, ordered_qty)
                    VALUES (?, ?, ?)
                """, (date, product, qty))
                if result.rowcount:
                    updated += 1
    else:
        orders = []

    # --- שלב 2: הערות מגיליון סיכום שבועי ---
    csv_summary = fetch_sheet_csv(sheet_id, gid=SUMMARY_GID)
    if csv_summary:
        notes_data = parse_summary_notes_from_csv(csv_summary)
        for item in notes_data:
            cursor.execute("""
                INSERT INTO weekly_summary (week_date, user_notes)
                VALUES (?, ?)
                ON CONFLICT(week_date) DO UPDATE SET user_notes = excluded.user_notes
            """, (item["week_date"], item["note"]))
            notes_updated += 1

    cursor.execute("SELECT COUNT(DISTINCT week_date) FROM weekly_orders")
    total_weeks = cursor.fetchone()[0]
    db.conn.commit()

    return {
        "success": True,
        "weeks_found": len(orders),
        "records_updated": updated,
        "notes_synced": notes_updated,
        "total_weeks_in_db": total_weeks
    }
