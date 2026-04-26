"""
bot.py - Main Telegram Bot for Gorlitz Weekly Orders
תפקיד: בוט ראשי ל-Telegram לניהול הזמנות שבועיות
"""

import os
import logging
import asyncio
from typing import Optional, Dict
from datetime import datetime, time
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters, JobQueue
)

from database import init_database, get_database
from weather import WeatherClient
from jewish_calendar import JewishCalendar
from recommender import OrderRecommender

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
ASKING_INVENTORY, ASKING_INVENTORY_MANUAL, ASKING_EXCEPTIONAL, SHOWING_SUMMARY = range(4)

# Product order for the questionnaire
PRODUCTS_ORDER = [
    "חלות מתוק",
    "רוגלך שוקולד",
    "רוגלך עלים קקאו",
    "קוקוש קייק",
    "קראנץ' קקאו",
    "גביניות",
    "פס שמרים קקאו שקית",
    "פס שמרים גבינה",
    "פס שוקולד פירורים",
]


def _make_qty_keyboard(idx: int) -> InlineKeyboardMarkup:
    """Create inline keyboard for quantity selection (0-10 + manual entry)"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("0", callback_data=f"qty:{idx}:0"),
            InlineKeyboardButton("1", callback_data=f"qty:{idx}:1"),
            InlineKeyboardButton("2", callback_data=f"qty:{idx}:2"),
            InlineKeyboardButton("3", callback_data=f"qty:{idx}:3"),
        ],
        [
            InlineKeyboardButton("4", callback_data=f"qty:{idx}:4"),
            InlineKeyboardButton("5", callback_data=f"qty:{idx}:5"),
            InlineKeyboardButton("6", callback_data=f"qty:{idx}:6"),
            InlineKeyboardButton("7", callback_data=f"qty:{idx}:7"),
        ],
        [
            InlineKeyboardButton("8", callback_data=f"qty:{idx}:8"),
            InlineKeyboardButton("9", callback_data=f"qty:{idx}:9"),
            InlineKeyboardButton("10", callback_data=f"qty:{idx}:10"),
            InlineKeyboardButton("✍️ הזן", callback_data=f"qty:{idx}:manual"),
        ],
    ])


class GorlitzBot:
    """בוט גרליץ לניהול הזמנות שבועיות"""

    def __init__(self):
        self.db = init_database()
        self.current_inventory = {}
        self.current_summary = {}
        self.current_recommendations = {}
        self.weather_forecast = {}
        self.holiday_factor = 1.0
        self.holiday_desc = ""

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "שלום! 👋\n\n"
            "אני בוט גרליץ לניהול הזמנות שבועיות.\n\n"
            "כל מוצאי שבת נסכם את המלאי ונכין הזמנה ליענקי.\n\n"
            "• /order - התחל סיכום שבוע\n"
            "• /products - רשימת מוצרים\n"
            "• /history - 5 הזמנות אחרונות\n"
            "• /help - עזרה"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 הוראות שימוש בבוט גרליץ\n\n"
            "/order - התחל סיכום שבוע חדש\n"
            "/products - רשימת כל המוצרים\n"
            "/history - סיכום של 5 הזמנות אחרונות\n"
            "/help - הצגת עמוד זה\n\n"
            "🥖 תהליך הזמנה:\n"
            "1. בחר /order\n"
            "2. לכל מוצר - לחץ כמה נשאר\n"
            "3. ענה על שאלת אירוע חריג\n"
            "4. קבל המלצה חכמה\n"
            "5. שלח ליענקי ב-WhatsApp\n\n"
            "📞 גרליץ (יענקי): +972-50-5603600"
        )

    async def products_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        products = self.db.get_all_products()
        message = "📦 רשימת מוצרים גרליץ:\n\n"
        for idx, product in enumerate(products, 1):
            name = product['name_he']
            buy = product['buy_price']
            sell = product['sell_price']
            margin = sell - buy
            message += f"{idx}. {name}\n"
            message += f"   קנייה: ₪{buy:.2f} | מכירה: ₪{sell:.2f} | רווח: ₪{margin:.2f}\n\n"
        await update.message.reply_text(message)

    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        recent = self.db.get_recent_weeks(weeks=5)
        message = "📊 5 הזמנות אחרונות:\n\n"
        for week in recent:
            date = week['week_date']
            profit = week.get('net_profit', 0)
            sales = week.get('sales_pct', 0)
            week_type = week.get('week_type', 'unknown')
            emoji = "✅" if profit > 200 else "⚠️" if profit > 0 else "❌"
            message += f"{emoji} {date} ({week_type})\n"
            message += f"   רווח: ₪{profit:.0f} | מכירות: {sales}%\n\n"
        await update.message.reply_text(message)

    async def order_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['inventory'] = {}
        context.user_data['exceptional'] = False
        context.user_data['exceptional_reason'] = None
        await update.message.reply_text(
            "שבוע טוב! 📋 בואו נסכם את השבוע\n\n"
            "לכל מוצר לחץ כמה יחידות נשארו על המדף:"
        )
        await self._send_product_question(update.message, 0)
        return ASKING_INVENTORY

    async def _send_product_question(self, message_obj, idx: int):
        product_name = PRODUCTS_ORDER[idx]
        total = len(PRODUCTS_ORDER)
        text = (
            f"📦 {idx + 1}/{total}\n"
            f"*{product_name}*\n\n"
            f"כמה נשאר על המדף?"
        )
        await message_obj.reply_text(
            text,
            reply_markup=_make_qty_keyboard(idx),
            parse_mode='Markdown'
        )

    async def handle_product_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.split(':')
        idx = int(parts[1])
        value = parts[2]
        if value == 'manual':
            context.user_data['manual_product_idx'] = idx
            product_name = PRODUCTS_ORDER[idx]
            await query.edit_message_text(
                f"✍️ {product_name}\n\nכמה בדיוק נשאר? כתוב מספר:",
                reply_markup=None
            )
            return ASKING_INVENTORY_MANUAL
        qty = int(value)
        product_name = PRODUCTS_ORDER[idx]
        context.user_data['inventory'][product_name] = qty
        next_idx = idx + 1
        if next_idx >= len(PRODUCTS_ORDER):
            await self._ask_exceptional(query)
            return ASKING_EXCEPTIONAL
        product_name_next = PRODUCTS_ORDER[next_idx]
        total = len(PRODUCTS_ORDER)
        text = (
            f"📦 {next_idx + 1}/{total}\n"
            f"*{product_name_next}*\n\n"
            f"כמה נשאר על המדף?"
        )
        await query.edit_message_text(
            text,
            reply_markup=_make_qty_keyboard(next_idx),
            parse_mode='Markdown'
        )
        return ASKING_INVENTORY

    async def handle_manual_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("⚠️ אנא כתוב מספר בלבד (לדוגמה: 12)")
            return ASKING_INVENTORY_MANUAL
        qty = int(text)
        if qty > 99:
            await update.message.reply_text("⚠️ כמות גדולה מדי (מקסימום 99)")
            return ASKING_INVENTORY_MANUAL
        idx = context.user_data.get('manual_product_idx', 0)
        product_name = PRODUCTS_ORDER[idx]
        context.user_data['inventory'][product_name] = qty
        next_idx = idx + 1
        if next_idx >= len(PRODUCTS_ORDER):
            await self._ask_exceptional_from_message(update.message)
            return ASKING_EXCEPTIONAL
        await self._send_product_question(update.message, next_idx)
        return ASKING_INVENTORY

    async def _ask_exceptional(self, query):
        await query.edit_message_text(
            "✅ סיכום מלאי נשמר!\n\nהאם קרה משהו חריג השבוע?\n(תיירים, עבודות, אירוע...)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ לא, שבוע רגיל", callback_data="exceptional_no"),
                InlineKeyboardButton("⚠️ כן, היה משהו", callback_data="exceptional_yes"),
            ]])
        )

    async def _ask_exceptional_from_message(self, message_obj):
        await message_obj.reply_text(
            "✅ מלאי נשמר!\n\nהאם קרה משהו חריג השבוע?\n(תיירים, עבודות, אירוע...)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ לא, שבוע רגיל", callback_data="exceptional_no"),
                InlineKeyboardButton("⚠️ כן, היה משהו", callback_data="exceptional_yes"),
            ]])
        )

    async def handle_exceptional_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data == "exceptional_no":
            context.user_data['exceptional'] = False
            await self.show_summary_and_recommendation(update, context)
            return SHOWING_SUMMARY
        elif query.data == "exceptional_yes":
            await query.edit_message_text(
                "מה קרה השבוע?\nבחר מהרשימה:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👥 הרבה תיירים", callback_data="event_tourists")],
                    [InlineKeyboardButton("🏗️ עבודות בניה", callback_data="event_construction")],
                    [InlineKeyboardButton("📦 בעיה בסחורה", callback_data="event_product_issue")],
                    [InlineKeyboardButton("❓ משהו אחר", callback_data="event_other")],
                ])
            )
            return ASKING_EXCEPTIONAL
        elif query.data.startswith("event_"):
            event_map = {
                "event_tourists": "הרבה תיירים השבוע",
                "event_construction": "עבודות בניה בסביבה",
                "event_product_issue": "בעיה בסחורה",
                "event_other": "אירוע חריג אחר",
            }
            context.user_data['exceptional'] = True
            context.user_data['exceptional_reason'] = event_map.get(query.data, "אירוע חריג")
            await self.show_summary_and_recommendation(update, context)
            return SHOWING_SUMMARY
        return ASKING_EXCEPTIONAL

    async def show_summary_and_recommendation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.edit_message_text("⏳ מחשב המלצה חכמה...")
        try:
            weather = await WeatherClient.get_friday_forecast()
        except Exception:
            weather = {'is_rainy': False, 'description_he': ''}
        self.weather_forecast = weather
        try:
            calendar = JewishCalendar()
            holiday_factor, holiday_desc = await calendar.get_holiday_factor()
        except Exception:
            holiday_factor, holiday_desc = 1.0, ''
        self.holiday_factor = holiday_factor
        self.holiday_desc = holiday_desc
        inventory = context.user_data.get('inventory', {})
        total_items = sum(inventory.values())
        # 0 נשאר = 100% מכירות, 10 נשאר = 70%, 20 נשאר = 40%
        sales_pct = max(40, min(100, 100 - total_items * 3))
        weather_factor = 0.80 if weather.get('is_rainy') else 1.0
        recommendations = OrderRecommender.calculate_recommendation(
            inventory,
            weather_factor=weather_factor,
            holiday_factor=holiday_factor,
            sales_pct=sales_pct,
            holiday_desc=holiday_desc
        )
        self.current_recommendations = recommendations
        summary = OrderRecommender.calculate_weekly_summary(inventory, sales_pct=sales_pct, recommendations=recommendations)
        self.current_summary = summary
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [
            "📊 סיכום השבוע:",
            "",
            f"💰 הכנסות משוערות: ₪{summary['total_revenue']:.0f}",
            f"💵 רווח נקי: ₪{summary['net_profit']:.0f}",
            f"📈 מכירות: {sales_pct}%",
        ]
        if weather.get('description_he'):
            lines.append(f"🌤️ שישי: {weather['description_he']}")
        if holiday_desc:
            lines.append(f"✡️ {holiday_desc}")
        if context.user_data.get('exceptional_reason'):
            lines.append(f"⚠️ {context.user_data['exceptional_reason']}")
        lines.extend(["", "📋 הזמנה מומלצת:", ""])
        total_cost = 0
        for name in sorted(recommendations.keys()):
            qty = recommendations[name]
            if qty > 0:
                product = self.db.get_product_by_name(name)
                cost = qty * product['buy_price']
                total_cost += cost
                lines.append(f"  • {name}: {qty} יח' (₪{cost:.0f})")
        lines.extend(["", f"💳 סה\"כ: ₪{total_cost:.0f}"])
        message_text = "\n".join(lines)
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "📱 שלח ליענקי גרליץ",
                    url=self._get_whatsapp_url(today)
                ),
            ]])
        )
        return SHOWING_SUMMARY

    def _get_whatsapp_url(self, week_date: str) -> str:
        message = OrderRecommender.format_order_message(
            self.current_recommendations,
            week_date,
            self.current_summary,
            self.weather_forecast.get('description_he', ''),
            self.holiday_desc
        )
        import urllib.parse
        encoded = urllib.parse.quote(message, safe='', encoding='utf-8')
        return f"https://wa.me/{GORLITZ_WHATSAPP}?text={encoded}"

    async def schedule_weekly_order(self, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Scheduled weekly order reminder")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.message:
                await update.message.reply_text("❌ משהו לא עבד. כתוב /order כדי להתחיל מחדש.")
            elif update and update.callback_query:
                await update.callback_query.message.reply_text("❌ משהו לא עבד. כתוב /order כדי להתחיל מחדש.")
        except Exception:
            pass


async def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot = GorlitzBot()
    job_queue = app.job_queue
    job_queue.run_daily(bot.schedule_weekly_order, time=time(21, 0), days=[5])
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("products", bot.products_command))
    app.add_handler(CommandHandler("history", bot.history_command))
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("order", bot.order_command)],
        states={
            ASKING_INVENTORY: [CallbackQueryHandler(bot.handle_product_button, pattern=r"^qty:")],
            ASKING_INVENTORY_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_manual_qty)],
            ASKING_EXCEPTIONAL: [CallbackQueryHandler(bot.handle_exceptional_event)],
            SHOWING_SUMMARY: [],
        },
        fallbacks=[CommandHandler("order", bot.order_command)],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
    app.add_error_handler(bot.error_handler)
    logger.info("Starting Gorlitz Bot...")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot is running!")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
