"""
config.py - Configuration and Constants for Gorlitz Bot
תפקיד: הגדרות מרכזיות וקבועים לבוט
"""

from datetime import time

# =============================================================================
# Configuration Constants
# =============================================================================

# Telegram Bot
TELEGRAM_REQUEST_TIMEOUT = 10
TELEGRAM_CONNECT_TIMEOUT = 10

# Database
DB_PATH = "gorlitz_bot.db"
DB_BACKUP_INTERVAL_DAYS = 7

# Weather
BNEI_BRAK_LATITUDE = 32.0833
BNEI_BRAK_LONGITUDE = 34.8333
WEATHER_FORECAST_DAYS = 7

# Scheduled Tasks
WEEKLY_ORDER_REMINDER_HOUR = 21
WEEKLY_ORDER_REMINDER_MINUTE = 0
WEEKLY_ORDER_REMINDER_DAY = 5  # Saturday (0=Monday, 5=Saturday)

# Gorlitz
GORLITZ_WHATSAPP_DEFAULT = "972505603600"
GORLITZ_MINIMUM_ORDER_NIS = 500
GORLITZ_AVERAGE_ORDER_NIS = 3500

# Recommendations
SALES_PERCENT_BASELINE = 70
WEATHER_RAINY_FACTOR = 0.80  # 20% reduction on rainy days
WEATHER_VERY_RAINY_FACTOR = 0.70  # 30% reduction on heavy rain
HOLIDAY_EVE_FACTOR = 1.5  # +50% on holiday eves
HOLIDAY_EREV_MAJOR_FACTOR = 1.6  # +60% on eve of major holidays
HOLIDAY_WEEK_AFTER_FACTOR = 0.9  # -10% week after holiday
HOLIDAY_YOM_KIPPUR_FACTOR = 0.7  # -30% on Yom Kippur

# Product Categories
SHELF_LIFE_PRODUCTS = {
    "רוגלך עלים קקאו": 2,  # Can hold 2 weeks
    "קוקוש קייק": 2  # Can hold 2 weeks
}

# Historical averages (from 23 weeks of data)
HISTORICAL_AVERAGES = {
    "normal_week_sales_pct": 65,
    "good_week_sales_pct": 80,
    "rainy_week_sales_pct": 51,
    "holiday_eve_sales_pct": 95,
    "post_holiday_sales_pct": 60
}

# Weather thresholds
RAIN_THRESHOLD_MM = 2
HEAVY_RAIN_THRESHOLD_MM = 10
HOT_THRESHOLD_CELSIUS = 28
WARM_THRESHOLD_CELSIUS = 22

# =============================================================================
# Product Database
# =============================================================================

PRODUCTS = [
    {
        "name_he": "חלות מתוק",
        "buy_price": 9.10,
        "sell_price": 18.00,
        "shelf_life_weeks": 1,
        "category": "challenges"
    },
    {
        "name_he": "רוגלך שוקולד",
        "buy_price": 17.50,
        "sell_price": 26.00,
        "shelf_life_weeks": 1,
        "category": "pastry"
    },
    {
        "name_he": "רוגלך עלים קקאו",
        "buy_price": 17.50,
        "sell_price": 26.00,
        "shelf_life_weeks": 2,
        "category": "pastry"
    },
    {
        "name_he": "קוקוש קייק",
        "buy_price": 22.40,
        "sell_price": 32.00,
        "shelf_life_weeks": 2,
        "category": "cake"
    },
    {
        "name_he": "קראנץ' קקאו",
        "buy_price": 19.60,
        "sell_price": 28.00,
        "shelf_life_weeks": 1,
        "category": "pastry"
    },
    {
        "name_he": "גביניות",
        "buy_price": 21.00,
        "sell_price": 31.00,
        "shelf_life_weeks": 1,
        "category": "pastry"
    },
    {
        "name_he": "פס שמרים גבינה",
        "buy_price": 15.00,
        "sell_price": 22.00,
        "shelf_life_weeks": 1,
        "category": "bread"
    },
    {
        "name_he": "פס שמרים קקאו שקית",
        "buy_price": 12.60,
        "sell_price": 18.00,
        "shelf_life_weeks": 1,
        "category": "bread"
    },
    {
        "name_he": "פס שוקולד פירורים",
        "buy_price": 19.60,
        "sell_price": 28.00,
        "shelf_life_weeks": 1,
        "category": "bread"
    }
]

# =============================================================================
# Jewish Holidays Impact
# =============================================================================

HOLIDAY_IMPACT = {
    "Pesach": {
        "factor": 1.5,
        "erev_factor": 1.6,
        "post_factor": 0.9,
        "description": "פסח",
        "emoji": "✡️"
    },
    "Rosh Hashana": {
        "factor": 1.4,
        "erev_factor": 1.5,
        "post_factor": 0.85,
        "description": "ראש השנה",
        "emoji": "✡️"
    },
    "Yom Kippur": {
        "factor": 0.7,
        "erev_factor": 0.8,
        "post_factor": 0.9,
        "description": "יום כיפור",
        "emoji": "⚪"
    },
    "Sukkot": {
        "factor": 1.3,
        "erev_factor": 1.4,
        "post_factor": 0.9,
        "description": "סוכות",
        "emoji": "✡️"
    },
    "Chanuka": {
        "factor": 1.2,
        "erev_factor": 1.3,
        "post_factor": 0.95,
        "description": "חנוכה",
        "emoji": "🕎"
    },
    "Purim": {
        "factor": 1.15,
        "erev_factor": 1.25,
        "post_factor": 0.95,
        "description": "פורים",
        "emoji": "🎭"
    },
    "Shavuot": {
        "factor": 1.2,
        "erev_factor": 1.3,
        "post_factor": 0.9,
        "description": "שבועות",
        "emoji": "✡️"
    }
}

# =============================================================================
# Exceptional Events Impact
# =============================================================================

EXCEPTIONAL_EVENTS = {
    "tourists": {
        "factor": 1.15,
        "description": "הרבה תיירים"
    },
    "construction": {
        "factor": 0.80,
        "description": "עבודות בניה"
    },
    "product_issue": {
        "factor": 0.75,
        "description": "בעיה בסחורה"
    },
    "special_event": {
        "factor": 1.25,
        "description": "אירוע מיוחד"
    },
    "other": {
        "factor": 1.0,
        "description": "אחר"
    }
}

# =============================================================================
# UI Strings (Hebrew)
# =============================================================================

UI_STRINGS = {
    "greeting": "שלום! 👋",
    "weekly_summary": "שבוע טוב! 📊 בואו נסכם את השבוע",
    "ask_inventory": "מה נשאר על המדף?",
    "ask_exceptional": "האם קרה משהו חריג השבוע?",
    "excellent_week": "✅ שבוע מעולה!",
    "good_week": "🟢 שבוע טוב",
    "normal_week": "🟡 שבוע רגיל",
    "bad_week": "🔴 שבוע קשה",
    "understood": "✅ הבנתי:",
    "send_to_whatsapp": "✅ שלח ליענקי גרליץ",
    "edit_order": "📋 ערוך הזמנה",
    "thank_you": "תודה! 🎯"
}

# =============================================================================
# Emoji Mappings
# =============================================================================

EMOJI = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "money": "💰",
    "chart": "📊",
    "product": "📦",
    "weather": "🌤️",
    "holiday": "✡️",
    "bread": "🥖",
    "phone": "📞",
    "date": "📅",
    "note": "📋",
    "rainy": "🌧️",
    "storm": "⛈️",
    "hot": "☀️",
    "cloudy": "⛅"
}
