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
        self.db_path = db_path
        self.conn = None
        self.init_db()

    def init_db(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name_he TEXT UNIQUE NOT NULL, buy_price REAL NOT NULL, sell_price REAL NOT NULL, shelf_life_weeks INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS weekly_summary (id INTEGER PRIMARY KEY AUTOINCREMENT, week_date DATE UNIQUE NOT NULL, total_cost REAL, total_revenue REAL, net_profit REAL, weather_rain BOOLEAN DEFAULT 0, holiday_type TEXT, was_exceptional BOOLEAN DEFAULT 0, exceptional_reason TEXT, sales_pct INTEGER, week_type TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.commit()
        self._load_products()
        self._load_historical_data()

    def _load_products(self):
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
                cursor.execute("INSERT INTO products (name_he, buy_price, sell_price, shelf_life_weeks) VALUES (?, ?, ?, ?)", (name, buy_price, sell_price, shelf_life))
            except: pass
        self.conn.commit()

    def _load_historical_data(self):
        historical_weeks = [
            ("2025-10-30","normal",65,False,None,13,106),
            ("2025-11-06","normal",65,False,None,35,58),
            ("2025-11-13","rainy",51,True,None,29,19),
            ("2025-11-20","bad",29,False,None,36,-260),
            ("2025-11-27","break",0,False,None,0,222),
            ("2025-12-04","normal",50,False,None,16,77),
            ("2025-12-11","normal",55,False,None,6,203),
            ("2025-12-18","normal",80,False,None,24,285),
            ("2025-12-25","bad_challah",42,False,"chanuka",23,30),
            ("2026-01-01","normal",56,False,None,25,100),
            ("2026-01-08","bad_challah",47,False,None,25,46),
            ("2026-01-15","good",73,False,None,5,262),
            ("2026-01-22","normal",68,False,None,5,209),
            ("2026-01-29","normal",56,False,None,16,0),
            ("2026-02-05","normal",60,False,None,14,240),
            ("2026-02-12","normal",90,False,None,4,588),
            ("2026-02-19","normal",90,False,None,4,0),
            ("2026-02-26","good",85,False,None,13,471),
            ("2026-03-05","normal",63,False,None,11,124),
            ("2026-03-12","normal",61,True,"purim_area",4,175),
            ("2026-03-19","good",73,False,None,5,244),
            ("2026-03-26","holiday_eve",100,False,"erev_pesach",0,411),
            ("2026-04-13","post_holiday",65,False,"post_pesach",10,0),
        ]
        cursor = self.conn.cursor()
        for date_str, week_type, sales_pct, weather_rain, holiday_type, waste_pct, net_profit in historical_weeks:
            try:
                cursor.execute("INSERT OR IGNORE INTO weekly_summary (week_date, week_type, sales_pct, weather_rain, holiday_type, net_profit) VALUES (?, ?, ?, ?, ?, ?)", (date_str, week_type, sales_pct, bool(weather_rain), holiday_type, net_profit))
            except: pass
        self.conn.commit()

    def get_all_products(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def get_product_by_name(self, name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM products WHERE name_he = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_weekly_summary(self, week_date, summary_data):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO weekly_summary (week_date, total_cost, total_revenue, net_profit, weather_rain, holiday_type, was_exceptional, exceptional_reason, sales_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (week_date, summary_data.get('total_cost'), summary_data.get('total_revenue'), summary_data.get('net_profit'), summary_data.get('weather_rain', False), summary_data.get('holiday_type'), summary_data.get('was_exceptional', False), summary_data.get('exceptional_reason'), summary_data.get('sales_pct')))
        self.conn.commit()

    def get_recent_weeks(self, weeks=10):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM weekly_summary ORDER BY week_date DESC LIMIT ?", (weeks,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        if self.conn: self.conn.close()


db = None

def init_database(db_path="gorlitz_bot.db"):
    global db
    db = GorlitzDatabase(db_path)
    return db

def get_database():
    global db
    if db is None: db = GorlitzDatabase()
    return db
