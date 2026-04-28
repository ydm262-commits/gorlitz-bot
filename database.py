"""
database.py - SQLite Database Setup and Management for Gorlitz Bot
תפקיד: ניהול בסיס הנתונים של פקודות שבועיות וסיכומים
"""

import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class GorlitzDatabase:
    """ניהול בסיס נתונים SQLite עבור בוט גרליץ"""

    def __init__(self, db_path: str = "gorlitz_bot.db"):
        """
        יצירת חיבור לבסיס הנתונים

        Args:
            db_path: נתיב לקובץ בסיס הנתונים
        """
        self.db_path = db_path
        self.conn = None
        self.init_db()

    def init_db(self):
        """יצירת טבלאות בבסיס הנתונים אם לא קיימות"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()

        # טבלת מוצרים
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_he TEXT UNIQUE NOT NULL,
                buy_price REAL NOT NULL,
                sell_price REAL NOT NULL,
                shelf_life_weeks INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # טבלת הזמנות שבועיות לפי מוצר
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_date DATE NOT NULL,
                product_name TEXT NOT NULL,
                ordered_qty INTEGER DEFAULT 0,
                UNIQUE(week_date, product_name)
            )
        """)

        # טבלת מלאי שבועי
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_date DATE NOT NULL UNIQUE,
                product_id INTEGER NOT NULL,
                remaining_qty INTEGER DEFAULT 0,
                wasted_qty INTEGER DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        # טבלת סיכום שבועי
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_date DATE UNIQUE NOT NULL,
                total_cost REAL,
                total_revenue REAL,
                net_profit REAL,
                weather_rain BOOLEAN DEFAULT 0,
                holiday_type TEXT,
                was_exceptional BOOLEAN DEFAULT 0,
                exceptional_reason TEXT,
                sales_pct INTEGER,
                week_type TEXT,
                user_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # הוספת עמודה לטבלה קיימת אם לא קיימת
        try:
            cursor.execute("ALTER TABLE weekly_summary ADD COLUMN user_notes TEXT")
        except Exception:
            pass

        # טבלת גורמים שנלמדו
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_factors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_type TEXT NOT NULL,
                factor_value REAL NOT NULL,
                confidence_score REAL DEFAULT 0.5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        self._load_products()
        self._load_historical_data()
        self._load_product_orders()

    def _load_products(self):
        """טעינת מוצרים בסיסיים אם לא קיימים"""
        products_data = [
            ("חלות מתוק", 9.10, 18.00, 1),
            ("רוגלך שוקולד", 17.50, 26.00, 1),
            ("רוגלך עלים קקאו", 17.50, 26.00, 2),
            ("קוקוש קייק", 22.40, 32.00, 2),
            ("קראנץ' קקאו", 19.60, 28.00, 1),
            ("גביניות", 21.00, 31.00, 1),
            ("פס שמרים גבינה", 15.00, 22.00, 1),
            ("פס שמרים קקאו שקית", 12.60, 18.00, 1),
            ("פס שוקולד פירורים", 19.60, 28.00, 1),
        ]

        cursor = self.conn.cursor()
        for name, buy_price, sell_price, shelf_life in products_data:
            try:
                cursor.execute("""
                    INSERT INTO products (name_he, buy_price, sell_price, shelf_life_weeks)
                    VALUES (?, ?, ?, ?)
                """, (name, buy_price, sell_price, shelf_life))
            except sqlite3.IntegrityError:
                # המוצר כבר קיים
                pass

        self.conn.commit()

    def _load_historical_data(self):
        """טעינת נתונים היסטוריים של 23 שבועות"""
        historical_weeks = [
            ("2025-10-30", "normal", 65, False, None, 13, 106),
            ("2025-11-06", "normal", 65, False, None, 35, 58),
            ("2025-11-13", "rainy", 51, True, None, 29, 19),
            ("2025-11-20", "bad", 29, False, None, 36, -260),
            ("2025-11-27", "break", 0, False, None, 0, 222),
            ("2025-12-04", "normal", 50, False, None, 16, 77),
            ("2025-12-11", "normal", 55, False, None, 6, 203),
            ("2025-12-18", "normal", 80, False, None, 24, 285),
            ("2025-12-25", "bad_challah", 42, False, "chanuka", 23, 30),
            ("2026-01-01", "normal", 56, False, None, 25, 100),
            ("2026-01-08", "bad_challah", 47, False, None, 25, 46),
            ("2026-01-15", "good", 73, False, None, 5, 262),
            ("2026-01-22", "normal", 68, False, None, 5, 209),
            ("2026-01-29", "normal", 56, False, None, 16, 0),
            ("2026-02-05", "normal", 60, False, None, 14, 240),
            ("2026-02-12", "normal", 90, False, None, 4, 588),
            ("2026-02-19", "normal", 90, False, None, 4, 0),
            ("2026-02-26", "good", 85, False, None, 13, 471),
            ("2026-03-05", "normal", 63, False, None, 11, 124),
            ("2026-03-12", "normal", 61, True, "purim_area", 4, 175),
            ("2026-03-19", "good", 73, False, None, 5, 244),
            ("2026-03-26", "holiday_eve", 100, False, "erev_pesach", 0, 411),
            ("2026-04-13", "post_holiday", 65, False, "post_pesach", 10, 0),
        ]

        cursor = self.conn.cursor()
        for date_str, week_type, sales_pct, weather_rain, holiday_type, waste_pct, net_profit in historical_weeks:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO weekly_summary
                    (week_date, week_type, sales_pct, weather_rain, holiday_type, net_profit)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (date_str, week_type, sales_pct, bool(weather_rain), holiday_type, net_profit))
            except sqlite3.IntegrityError:
                pass

        self.conn.commit()

    def _load_product_orders(self):
        """טעינת נתוני הזמנות היסטוריות לפי מוצר — 24 שבועות"""
        WEEKLY_ORDERS = [
            ("2025-10-30", {"חלות מתוק":6,"רוגלך שוקולד":6,"רוגלך עלים קקאו":3,"קוקוש קייק":4,"קראנץ' קקאו":4,"פס שוקולד פירורים":0,"פס שמרים קקאו שקית":0,"פס שמרים גבינה":2,"גביניות":6}),
            ("2025-11-06", {"חלות מתוק":6,"רוגלך שוקולד":8,"רוגלך עלים קקאו":2,"קוקוש קייק":2,"קראנץ' קקאו":4,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":0,"פס שמרים גבינה":2,"גביניות":6}),
            ("2025-11-13", {"חלות מתוק":6,"רוגלך שוקולד":8,"רוגלך עלים קקאו":2,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":0,"פס שמרים גבינה":2,"גביניות":5}),
            ("2025-11-20", {"חלות מתוק":12,"רוגלך שוקולד":8,"רוגלך עלים קקאו":3,"קוקוש קייק":0,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":0,"פס שמרים גבינה":3,"גביניות":5}),
            ("2025-12-04", {"חלות מתוק":6,"רוגלך שוקולד":15,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":1,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":0}),
            ("2025-12-11", {"חלות מתוק":6,"רוגלך שוקולד":10,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":3,"גביניות":3}),
            ("2025-12-18", {"חלות מתוק":12,"רוגלך שוקולד":6,"רוגלך עלים קקאו":3,"קוקוש קייק":0,"קראנץ' קקאו":0,"פס שוקולד פירורים":1,"פס שמרים קקאו שקית":5,"פס שמרים גבינה":3,"גביניות":5}),
            ("2025-12-25", {"חלות מתוק":12,"רוגלך שוקולד":5,"רוגלך עלים קקאו":5,"קוקוש קייק":3,"קראנץ' קקאו":0,"פס שוקולד פירורים":0,"פס שמרים קקאו שקית":6,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-01-01", {"חלות מתוק":12,"רוגלך שוקולד":8,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":2,"פס שמרים גבינה":3,"גביניות":5}),
            ("2026-01-08", {"חלות מתוק":12,"רוגלך שוקולד":3,"רוגלך עלים קקאו":0,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":8,"פס שמרים גבינה":3,"גביניות":5}),
            ("2026-01-15", {"חלות מתוק":6,"רוגלך שוקולד":8,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":5,"פס שמרים גבינה":3,"גביניות":5}),
            ("2026-01-22", {"חלות מתוק":6,"רוגלך שוקולד":12,"רוגלך עלים קקאו":0,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":0,"פס שמרים קקאו שקית":4,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-01-29", {"חלות מתוק":6,"רוגלך שוקולד":6,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":5,"פס שמרים גבינה":3,"גביניות":5}),
            ("2026-02-05", {"חלות מתוק":6,"רוגלך שוקולד":6,"רוגלך עלים קקאו":3,"קוקוש קייק":0,"קראנץ' קקאו":4,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":2,"פס שמרים גבינה":2,"גביניות":6}),
            ("2026-02-12", {"חלות מתוק":6,"רוגלך שוקולד":14,"רוגלך עלים קקאו":0,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":0,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-02-19", {"חלות מתוק":6,"רוגלך שוקולד":6,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":2,"פס שמרים גבינה":3,"גביניות":6}),
            ("2026-02-26", {"חלות מתוק":6,"רוגלך שוקולד":14,"רוגלך עלים קקאו":0,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-03-05", {"חלות מתוק":6,"רוגלך שוקולד":14,"רוגלך עלים קקאו":0,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-03-12", {"חלות מתוק":0,"רוגלך שוקולד":14,"רוגלך עלים קקאו":4,"קוקוש קייק":2,"קראנץ' קקאו":0,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-03-19", {"חלות מתוק":0,"רוגלך שוקולד":13,"רוגלך עלים קקאו":0,"קוקוש קייק":0,"קראנץ' קקאו":2,"פס שוקולד פירורים":3,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-03-26", {"חלות מתוק":18,"רוגלך שוקולד":0,"רוגלך עלים קקאו":0,"קוקוש קייק":0,"קראנץ' קקאו":2,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":5,"פס שמרים גבינה":2,"גביניות":6}),
            ("2026-04-16", {"חלות מתוק":0,"רוגלך שוקולד":12,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":2,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":4,"פס שמרים גבינה":2,"גביניות":5}),
            ("2026-04-23", {"חלות מתוק":0,"רוגלך שוקולד":14,"רוגלך עלים קקאו":3,"קוקוש קייק":2,"קראנץ' קקאו":2,"פס שוקולד פירורים":2,"פס שמרים קקאו שקית":3,"פס שמרים גבינה":2,"גביניות":5}),
        ]
        cursor = self.conn.cursor()
        for date_str, products in WEEKLY_ORDERS:
            for product_name, qty in products.items():
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO weekly_orders (week_date, product_name, ordered_qty)
                        VALUES (?, ?, ?)
                    """, (date_str, product_name, qty))
                except Exception:
                    pass
        self.conn.commit()

    def get_product_order_history(self) -> dict:
        """ממוצע הזמנות לפי מוצר מהיסטוריה אמיתית"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT product_name,
                   ROUND(AVG(ordered_qty), 1) as avg_qty,
                   MIN(ordered_qty) as min_qty,
                   MAX(ordered_qty) as max_qty,
                   COUNT(*) as weeks_ordered
            FROM weekly_orders
            WHERE ordered_qty > 0
            GROUP BY product_name
        """)
        return {row[0]: {"avg": row[1], "min": row[2], "max": row[3], "weeks": row[4]}
                for row in cursor.fetchall()}

    def get_recent_product_orders(self, weeks: int = 6) -> List[Dict]:
        """הזמנות אחרונות לפי שבוע"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT week_date, product_name, ordered_qty
            FROM weekly_orders
            ORDER BY week_date DESC
            LIMIT ?
        """, (weeks * 9,))
        rows = cursor.fetchall()
        # מארגן לפי שבוע
        by_week = {}
        for date, product, qty in rows:
            if date not in by_week:
                by_week[date] = {}
            by_week[date][product] = qty
        return [{"week_date": d, "orders": o} for d, o in sorted(by_week.items(), reverse=True)]

    def get_all_products(self) -> List[Dict]:
        """קבלת רשימת כל המוצרים"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def get_product_by_name(self, name: str) -> Optional[Dict]:
        """קבלת מוצר לפי שם"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM products WHERE name_he = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_weekly_summary(self, week_date: str, summary_data: Dict, user_notes: str = ""):
        """שמירת סיכום שבועי"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO weekly_summary
            (week_date, total_cost, total_revenue, net_profit, weather_rain,
             holiday_type, was_exceptional, exceptional_reason, sales_pct, user_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            week_date,
            summary_data.get('total_cost'),
            summary_data.get('total_revenue'),
            summary_data.get('net_profit'),
            summary_data.get('weather_rain', False),
            summary_data.get('holiday_type'),
            summary_data.get('was_exceptional', False),
            summary_data.get('exceptional_reason'),
            summary_data.get('sales_pct'),
            user_notes or ""
        ))
        self.conn.commit()

    def get_weekly_summary(self, week_date: str) -> Optional[Dict]:
        """קבלת סיכום שבועי"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM weekly_summary WHERE week_date = ?", (week_date,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_recent_weeks(self, weeks: int = 10) -> List[Dict]:
        """קבלת הנתונים של השבועות האחרונים"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM weekly_summary
            ORDER BY week_date DESC
            LIMIT ?
        """, (weeks,))
        return [dict(row) for row in cursor.fetchall()]

    def get_average_sales_pct(self) -> float:
        """חישוב אחוז מכירות ממוצע"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT AVG(sales_pct) FROM weekly_summary WHERE sales_pct > 0")
        result = cursor.fetchone()[0]
        return result if result else 70

    def close(self):
        """סגירת חיבור לבסיס הנתונים"""
        if self.conn:
            self.conn.close()


# יצירת instance גלובלי של בסיס הנתונים
db = None

def init_database(db_path: str = "gorlitz_bot.db") -> GorlitzDatabase:
    """אתחול בסיס הנתונים"""
    global db
    db = GorlitzDatabase(db_path)
    return db

def get_database() -> GorlitzDatabase:
    """קבלת instance של בסיס הנתונים"""
    global db
    if db is None:
        db = GorlitzDatabase()
    return db
