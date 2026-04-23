"""
bot.py - Main Telegram Bot for Gorlitz Weekly Orders
תפקיד: בוט ראשי ל-Telegram לניהול הזמנות שבועיות מגרליץ
"""

import os
import logging
from typing import Optional, Dict
from datetime import datetime, time
from dotenv import load_dotenv

from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters, JobQueue
)
from telegram.constants import ChatAction

from database import init_database, get_database
from weather import WeatherClient
from jewish_calendar import JewishCalendar
from recommender import OrderRecommender
from voice_handler import VoiceTranscriber, parse_inventory_text

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GORLITZ_WHATSAPP = os.getenv('GORLITZ_WHATSAPP', '972505603600')

# Conversation states
ASKING_INVENTORY, ASKING_EXCEPTIONAL, SHOWING_SUMMARY = range(3)


class GorlitzBot:
    """בוט גרליץ לניהול הזמנות שבועיות"""

    def __init__(self):
        """אתחול הבוט"""
        self.db = init_database()
        self.voice_transcriber = VoiceTranscriber()  # No API key needed
        self.current_inventory = {}
        self.current_summary = {}
        self.current_recommendations = {}
        self.weather_forecast = {}
        self.holiday_factor = 1.0
        self.holiday_desc = ""

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /start - התחלת השיחה עם הבוט
        """
        await update.message.reply_text(
            "שלום! 👋\n\n"
            "אני בוט גרליץ שיעזור לך לנהל הזמנות שבועיות.\n\n"
            "כל מוצאי שבת (בערך בשעה 21:00) אנחנו נעדכן את מלאי גרליץ.\n\n"
            "הוראות:\n"
            "• /order - התחל סיכום שבוע\n"
            "• /products - רשימת מוצרים\n"
            "• /help - עזרה"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /help - הצגת הוראות
        """
        help_text = """
📋 הוראות שימוש בבוט גרליץ

/order - התחל סיכום שבוע חדש
/products - רשימת כל המוצרים וההחזקות
/history - סיכום של 5 הזמנות אחרונות
/help - הצגת עמוד זה
/start - התחלה

🥖 תהליך הזמנה:
1. בחר /order
2. ספר כמה מכל מוצר נשאר על המדף
3. ענה על שאלות לגבי אירועים חריגים
4. ראה סיכום וההמלצה
5. שלח להזמנה ליענקי ב-WhatsApp

💡 טיפים:
• יכול לרשום בטקסט: "חלות 3, רוגלך 2"
• או בקוד קצר: "ח3 ר2"
• או להשלוח הודעה קולית

📞 גרליץ (יענקי): +972-50-5603600
"""
        await update.message.reply_text(help_text)

    async def products_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /products - הצגת רשימת מוצרים
        """
        products = self.db.get_all_products()

        message = "📦 רשימת מוצרים גרליץ:\n\n"
        for idx, product in enumerate(products, 1):
            name = product['name_he']
            buy = product['buy_price']
            sell = product['sell_price']
            margin = sell - buy
            margin_pct = (margin / buy) * 100

            message += f"{idx}. {name}\n"
            message += f"   קנייה: ₪{buy:.2f} | מכירה: ₪{sell:.2f} | רווח: ₪{margin:.2f} ({margin_pct:.0f}%)\n\n"

        await update.message.reply_text(message)

    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /history - הצגת היסטוריית הזמנות
        """
        recent = self.db.get_recent_weeks(weeks=5)

        message = "📊 5 הזמנות אחרונות:\n\n"
        for week in recent:
            date = week['week_date']
            profit = week.get('net_profit', 0)
            sales = week.get('sales_pct', 0)
            week_type = week.get('week_type', 'unknown')

            profit_emoji = "✅" if profit > 200 else "⚠️" if profit > 0 else "❌"

            message += f"{profit_emoji} {date} ({week_type})\n"
            message += f"   רווח: ₪{profit:.0f} | מכירות: {sales}%\n\n"

        await update.message.reply_text(message)

    async def order_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /order - התחלת תהליך הסיכום השבועי
        """
        # איפוס משתנים
        context.user_data['inventory'] = {}
        context.user_data['exceptional'] = False
        context.user_data['exceptional_reason'] = None

        # שלב 1: בקש מלאי
        await update.message.reply_text(
            "שבוע טוב! 📊 בואו נסכם את השבוע\n\n"
            "מה נשאר על המדף?",
            reply_markup=ReplyKeyboardMarkup(
                [["🎤 הודעה קולית"], ["💬 כתב טקסט"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )

        return ASKING_INVENTORY

    async def handle_inventory_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        טיפול בקלט מלאי (טקסט או קול)
        """
        if update.message.voice:
            # הודעה קולית - לא נתמכת
            await update.message.reply_text(
                "אנא שלח טקסט עם מה שנשאר 🙏\n\n"
                "דוגמה: חלות 3, רוגלך שוקולד 2, גביניות 1"
            )
            return ASKING_INVENTORY

        elif update.message.text:
            # ניתוח טקסט
            text = update.message.text

            if text in ["🎤 הודעה קולית", "💬 כתב טקסט"]:
                await update.message.reply_text(
                    "בואו נתחיל!\n"
                    "כתוב לי את ההערכה של מה שנשאר:\n\n"
                    "דוגמה: חלות 3, רוגלך שוקולד 2, גביניות 1"
                )
                return ASKING_INVENTORY

            # פרסם את הטקסט
            inventory = await parse_inventory_text(text)

            if not inventory or all(v == 0 for v in inventory.values()):
                await update.message.reply_text(
                    "❌ לא הצלחתי להבין. בואו נחזור:\n\n"
                    "כתוב ככה: חלות 3, רוגלך שוקולד 2"
                )
                return ASKING_INVENTORY

        else:
            return ASKING_INVENTORY

        # שמור את המלאי
        context.user_data['inventory'] = inventory
        self.current_inventory = inventory

        # הצג מה הבנתי
        message = "✅ הבנתי:\n\n"
        for product, qty in sorted(inventory.items()):
            message += f"  • {product}: {qty}\n"

        message += "\nתודה! 🎯"

        await update.message.reply_text(
            message,
            reply_markup=ReplyKeyboardMarkup(
                [["✅ בדיוק"], ["❌ תיקון"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )

        return ASKING_INVENTORY

    async def confirm_or_fix_inventory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        אישור או תיקון המלאי
        """
        if update.message.text == "❌ תיקון":
            await update.message.reply_text(
                "בואו נחזור!\n"
                "כתוב שוב את המלאי:"
            )
            return ASKING_INVENTORY

        # המלאי אושר - עבור לשלב הבא
        await update.message.reply_text(
            "מעולה! 📋\n\n"
            "עכשיו שאלה אחרונה:\n"
            "האם קרה השתמשים חריג השבוע?\n"
            "(למשל: הרבה תיירים, עבודות בניה, בעיה בסחורה...)",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("כן - ספר לי", callback_data="exceptional_yes"),
                    InlineKeyboardButton("לא, רגיל", callback_data="exceptional_no")
                ]
            ])
        )

        return ASKING_EXCEPTIONAL

    async def handle_exceptional_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        טיפול בשאלה על אירוע חריג
        """
        query = update.callback_query
        await query.answer()

        if query.data == "exceptional_no":
            context.user_data['exceptional'] = False
            await self.show_summary_and_recommendation(update, context)
            return SHOWING_SUMMARY

        # הוא בחר כן
        await query.edit_message_text(
            "בואו אספר לי עוד:\n"
            "מה קרה השבוע?\n\n"
            "(שלח הודעה או בחר מהאפשרויות)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("הרבה תיירים", callback_data="event_tourists")],
                [InlineKeyboardButton("עבודות בניה", callback_data="event_construction")],
                [InlineKeyboardButton("בעיה בסחורה", callback_data="event_product_issue")],
                [InlineKeyboardButton("משהו אחר", callback_data="event_other")]
            ])
        )

        return ASKING_EXCEPTIONAL

    async def show_summary_and_recommendation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        הצגת סיכום וההמלצה
        """
        # קבל מידע על מזג אוויר
        weather = await WeatherClient.get_friday_forecast()
        self.weather_forecast = weather

        # קבל מידע על חגים
        calendar = JewishCalendar()
        holiday_factor, holiday_desc = await calendar.get_holiday_factor()
        self.holiday_factor = holiday_factor
        self.holiday_desc = holiday_desc

        # חישוב כמות מכירות משוערת
        inventory = context.user_data.get('inventory', {})
        total_items = sum(inventory.values())
        sales_pct = max(50, min(100, int(70 + (total_items - 10) * 2)))

        # חישוב המלצה
        weather_factor = 0.80 if weather.get('is_rainy') else 1.0
        recommendations = OrderRecommender.calculate_recommendation(
            inventory,
            weather_factor=weather_factor,
            holiday_factor=holiday_factor,
            sales_pct=sales_pct
        )
        self.current_recommendations = recommendations

        # חישוב סיכום
        summary = OrderRecommender.calculate_weekly_summary(
            inventory,
            sales_pct=sales_pct
        )
        self.current_summary = summary

        # בניית ההודעה
        today = datetime.now().strftime("%Y-%m-%d")

        message_lines = [
            "📊 סיכום השבוע:",
            "",
            f"💰 סיכום כלכלי:",
            f"  הכנסות משוערות: ₪{summary['total_revenue']:.0f}",
            f"  רווח נקי: ₪{summary['net_profit']:.0f}",
            "",
            f"📈 מכירות: {sales_pct}%",
            f"📦 מלאי כרגע: {total_items} יח'",
            ""
        ]

        if weather.get('description_he'):
            message_lines.append(f"🌤️ מזג אוויר שישי: {weather['description_he']}")
        if holiday_desc:
            message_lines.append(f"✡️ {holiday_desc}")

        message_lines.extend([
            "",
            "📋 הזמנה מומלצת ליום שישי:",
            ""
        ])

        total_cost = 0
        for product_name in sorted(self.current_recommendations.keys()):
            qty = self.current_recommendations[product_name]
            if qty > 0:
                product = self.db.get_product_by_name(product_name)
                cost = qty * product['buy_price']
                total_cost += cost
                message_lines.append(f"  • {product_name}: {qty} יח' (₪{cost:.0f})")

        message_lines.extend([
            "",
            f"💳 סה״כ הזמנה: ₪{total_cost:.0f}",
            "",
            f"(ממוצע הזמנה: ₪{OrderRecommender.MINIMUM_ORDER_NIS})"
        ])

        message_text = "\n".join(message_lines)

        # שלח עם כפתור להזמנה
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ שלח ליענקי גרליץ",
                        url=self._get_whatsapp_url(today)
                    )],
                    [InlineKeyboardButton(
                        "📋 ערוך הזמנה",
                        callback_data="edit_order"
                    )]
                ])
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ שלח ליענקי גרליץ",
                        url=self._get_whatsapp_url(today)
                    )],
                    [InlineKeyboardButton(
                        "📋 ערוך הזמנה",
                        callback_data="edit_order"
                    )]
                ])
            )

        return SHOWING_SUMMARY

    def _get_whatsapp_url(self, week_date: str) -> str:
        """
        בניית URL של WhatsApp עם הודעת הזמנה

        Args:
            week_date: תאריך השבוע

        Returns:
            str: URL עם יודעת הזמנה
        """
        message = OrderRecommender.format_order_message(
            self.current_recommendations,
            week_date,
            self.current_summary,
            self.weather_forecast.get('description_he', ''),
            self.holiday_desc
        )

        # קידוד ל-URL
        import urllib.parse
        encoded_message = urllib.parse.quote(message)

        return f"https://wa.me/{GORLITZ_WHATSAPP}?text={encoded_message}"

    async def schedule_weekly_order(self, context: ContextTypes.DEFAULT_TYPE):
        """
        משימה מתוזמנת - הפעלת סיכום שבועי כל מוצאי שבת
        """
        # בואו נשליח הודעה לכל המשתמשים הנרשמים
        logger.info("Scheduled weekly order reminder sent")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        טיפול בשגיאות
        """
        logger.error(f"Update {update} caused error {context.error}")
        if update.message:
            await update.message.reply_text(
                "❌ משהו לא עבד טוב. בואו נחזור לתחילה.\n"
                "כתוב /order כדי להתחיל מחדש."
            )


async def main():
    """
    פונקציה ראשית - הפעלת הבוט
    """
    # בדיקת משתנים חייבים
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    # יצירת application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # אתחול בוט
    bot = GorlitzBot()

    # קבע מטלות
    job_queue = app.job_queue

    # כל מוצאי שבת בשעה 21:00 (9 PM בשעון ישראל)
    job_queue.run_daily(
        bot.schedule_weekly_order,
        time=time(21, 0),
        days=[5]  # 5 = Saturday (0 = Monday)
    )

    # הוסף handlers
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("products", bot.products_command))
    app.add_handler(CommandHandler("history", bot.history_command))

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("order", bot.order_command)],
        states={
            ASKING_INVENTORY: [
                MessageHandler(filters.VOICE, bot.handle_inventory_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inventory_input),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    bot.confirm_or_fix_inventory
                ),
            ],
            ASKING_EXCEPTIONAL: [
                CallbackQueryHandler(bot.handle_exceptional_event),
            ],
            SHOWING_SUMMARY: [
                CallbackQueryHandler(bot.show_summary_and_recommendation),
            ]
        },
        fallbacks=[CommandHandler("order", bot.order_command)],
    )

    app.add_handler(conv_handler)
    app.add_error_handler(bot.error_handler)

    # התחל את הבוט
    logger.info("Starting Gorlitz Bot...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
