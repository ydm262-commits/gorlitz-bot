"""
sheets_sync.py - סנכרון נתונים מגוגל שיטס לבסיס הנתונים
מושך את גיליון בקרת_מאפייה ומעדכן weekly_orders בכל שבוע חדש
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
    מנתח CSV של הגיליון ומוצא את טבלת ההזמנות המפורטות.
    מחפש שורה שמתחילה ב'שבוע' ואחריה תאריך ומספרים.
    """
    orders = []
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # חפש את תחילת טבלת ההזמנות
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

            # המר תאריך מ-DD/MM/YYYY ל-YYYY-MM-DD
            parts = date_str.split('/')
            if len(parts) == 3:
                iso_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            else:
                continue

            # קרא כמויות (עמודות 2 עד 10)
            qtys = {}
            for j, product in enumerate(PRODUCT_COLS):
                try:
                    qty = int(row[j + 2].strip()) if j + 2 < len(row) else 0
                    qtys[product] = qty
                except (ValueError, IndexError):
                    qtys[product] = 0

            # דלג על שבועות ריקים
            if sum(qtys.values()) == 0:
                continue

            orders.append({"week_date": iso_date, "orders": qtys})
        except Exception as e:
            continue

    return orders


def sync_from_google_sheets() -> Dict:
    """
    מסנכרן את כל הנתונים מגוגל שיטס לבסיס הנתונים.
    מחזיר סטטוס של הסנכרון.
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        return {"success": False, "error": "GOOGLE_SHEET_ID לא מוגדר"}

    # שלב 1: משוך את הגיליון
    csv_text = fetch_sheet_csv(sheet_id)
    if not csv_text:
        return {"success": False, "error": "לא ניתן לגשת לגיליון"}

    # שלב 2: נתח
    orders = parse_orders_from_csv(csv_text)
    if not orders:
        return {"success": False, "error": "לא נמצאו נתוני הזמנות"}

    # שלב 3: שמור בבסיס הנתונים
    db = get_database()
    cursor = db.conn.cursor()
    new_weeks = 0
    updated = 0

    for week_data in orders:
        date = week_data["week_date"]
        for product, qty in week_data["orders"].items():
            result = cursor.execute("""
                INSERT OR REPLACE INTO weekly_orders (week_date, product_name, ordered_qty)
                VALUES (?, ?, ?)
            """, (date, product, qty))
            if result.rowcount:
                updated += 1

    # בדוק כמה שבועות חדשים
    cursor.execute("SELECT COUNT(DISTINCT week_date) FROM weekly_orders")
    total_weeks = cursor.fetchone()[0]

    db.conn.commit()

    return {
        "success": True,
        "weeks_found": len(orders),
        "records_updated": updated,
        "total_weeks_in_db": total_weeks
    }
