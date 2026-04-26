"""
recommender.py - Smart Recommendation Engine for Gorlitz Bot
תפקיד: חישוב הזמנות מומלצות בהתאם לנתונים היסטוריים וגורמים חיצוניים
"""

from typing import Dict, List, Optional
from database import get_database
from datetime import datetime


class OrderRecommender:
    """מנוע מומלץ הזמנות חכם"""

    # מחיר מינימלי להזמנה מגרליץ
    MINIMUM_ORDER_NIS = 500

    # מוצרים שיכולים להחזיק שבועיים
    TWO_WEEK_PRODUCTS = ["רוגלך עלים קקאו", "קוקוש קייק"]

    @staticmethod
    def calculate_baseline_recommendation() -> Dict[str, int]:
        """
        חישוב כמות בסיסית מומלצת לכל מוצר על סמך נתונים היסטוריים

        Returns:
            dict: {product_name: recommended_quantity}
        """
        db = get_database()
        products = db.get_all_products()

        # קבל את השבועות הרגילים האחרונים (ללא חגים או שבועות חריגות)
        recent_weeks = db.get_recent_weeks(weeks=15)
        normal_weeks = [w for w in recent_weeks if w.get('week_type') == 'normal']

        baseline = {}

        for product in products:
            product_name = product['name_he']
            sell_price = product['sell_price']
            buy_price = product['buy_price']

            # ממוצע של 70% מכירות בשבועות רגילים
            avg_sales_pct = db.get_average_sales_pct()
            if normal_weeks:
                avg_sales_pct = sum(w['sales_pct'] for w in normal_weeks) / len(normal_weeks)

            # חישוב כמות בסיסית
            # בהנחה שהחנות קנתה בקופ"ח ~3000-4000 שקלים בשבוע ממוצע
            avg_budget = 3500
            sales_factor = avg_sales_pct / 100

            # כמות משוערת
            estimated_qty = int((avg_budget * sales_factor) / buy_price)

            # וודא כמות סבירה (בין 2 ל-20 יחידות לרוב)
            estimated_qty = max(2, min(20, estimated_qty))

            baseline[product_name] = estimated_qty

        return baseline

    @staticmethod
    def calculate_recommendation(
        inventory_left: Dict[str, int],
        weather_factor: float = 1.0,
        holiday_factor: float = 1.0,
        sales_pct: int = 70
    ) -> Dict[str, int]:
        """
        חישוב כמויות הזמנה מומלצות

        Args:
            inventory_left: מלאי שנשאר {product_name: qty}
            weather_factor: מקדם מזג אוויר (0.7-1.0)
            holiday_factor: מקדם חג (0.7-1.6)
            sales_pct: אחוז מכירות משוער

        Returns:
            dict: {product_name: recommended_qty}
        """
        db = get_database()
        products = db.get_all_products()
        baseline = OrderRecommender.calculate_baseline_recommendation()

        recommendations = {}

        for product in products:
            name = product['name_he']
            buy_price = product['buy_price']

            # כמות בסיסית
            base_qty = baseline.get(name, 5)

            # החל מקדמים
            adjusted_qty = base_qty * weather_factor * holiday_factor

            # הוסף מקדם אחוז מכירות
            adjusted_qty *= (sales_pct / 70)  # 70 = ממוצע

            # מלאי נוכחי
            current_inventory = inventory_left.get(name, 0)
            qty_to_order = int(max(0, adjusted_qty - current_inventory))

            # עגל לכמות סבירה
            if qty_to_order > 0:
                qty_to_order = max(1, round(qty_to_order))

            recommendations[name] = qty_to_order

        # וודא הזמנה מינימלית
        total_cost = sum(recommendations[name] * db.get_product_by_name(name)['buy_price']
                        for name in recommendations if recommendations[name] > 0)

        if total_cost < OrderRecommender.MINIMUM_ORDER_NIS:
            # הוסף מוצרים עד שנגיע להזמנה מינימלית
            shortage = OrderRecommender.MINIMUM_ORDER_NIS - total_cost
            for name in recommendations:
                if recommendations[name] > 0:
                    product = db.get_product_by_name(name)
                    additional = int(shortage / product['buy_price'])
                    if additional > 0:
                        recommendations[name] += additional
                        shortage -= additional * product['buy_price']
                        if shortage <= 0:
                            break

        return {k: v for k, v in recommendations.items() if v > 0}

    @staticmethod
    def calculate_weekly_summary(
        inventory_left: Dict[str, int],
        sales_pct: int,
        recommendations: Dict[str, int] = None,
        was_exceptional: bool = False,
        exceptional_reason: str = None
    ) -> Dict:
        """
        חישוב סיכום שבועי (מחיר, הכנסות, רווח) - מחירים אמיתיים מ-DB

        Args:
            inventory_left: מלאי שנשאר
            sales_pct: אחוז מכירות
            recommendations: כמויות מוזמנות {product_name: qty}
            was_exceptional: האם היה אירוע חריג
            exceptional_reason: תיאור האירוע החריג

        Returns:
            dict: סיכום שבועי עם חישובים אמיתיים
        """
        db = get_database()
        total_cost = 0.0
        total_revenue = 0.0

        if recommendations:
            for product_name, qty in recommendations.items():
                if qty > 0:
                    product = db.get_product_by_name(product_name)
                    if product:
                        total_cost += qty * product['buy_price']
                        total_revenue += qty * product['sell_price'] * (sales_pct / 100)
        else:
            products = db.get_all_products()
            for p in products:
                total_cost += 5 * p['buy_price']
                total_revenue += 5 * p['sell_price'] * (sales_pct / 100)

        waste_pct = max(0, 100 - sales_pct)
        waste_loss = total_cost * (waste_pct / 100)
        net_profit = total_revenue - total_cost

        return {
            "total_cost": round(total_cost, 2),
            "total_revenue": round(total_revenue, 2),
            "net_profit": round(net_profit, 2),
            "waste_pct": waste_pct,
            "waste_loss": round(waste_loss, 2),
            "sales_pct": sales_pct,
            "was_exceptional": was_exceptional,
            "exceptional_reason": exceptional_reason
        }

    @staticmethod
    def format_order_message(
        recommendations: Dict[str, int],
        week_date: str,
        summary: Dict,
        weather_desc: str = "",
        holiday_desc: str = ""
    ) -> str:
        """
        עיצוב הודעת הזמנה לWhatsApp

        Args:
            recommendations: כמויות מומלצות
            week_date: תאריך השבוע
            summary: סיכום שבועי
            weather_desc: תיאור מזג אוויר
            holiday_desc: תיאור חג

        Returns:
            str: הודעת WhatsApp עברית מעוצבת
        """
        db = get_database()

        lines = [
            f"הזמנה מגרליץ",
            f"שבוע {week_date}",
            "",
            "פירוט הזמנה:"
        ]

        total_cost = 0
        for product_name, qty in sorted(recommendations.items()):
            if qty > 0:
                product = db.get_product_by_name(product_name)
                cost = qty * product['buy_price']
                total_cost += cost
                lines.append(f"  {product_name}: {qty} יח' ({cost:.0f} ש\"ח)")

        lines.extend([
            "",
            f"סה\"כ: {total_cost:.0f} ש\"ח",
        ])

        if weather_desc:
            lines.append(f"מזג אוויר: {weather_desc}")

        if holiday_desc:
            lines.append(f"הערה: {holiday_desc}")

        lines.extend([
            "",
            "תודה רבה, יענקי!"
        ])

        return "\n".join(lines)

    @staticmethod
    def estimate_next_week_performance(
        weather_forecast: Dict,
        holiday_factor: float,
        current_inventory: Dict[str, int]
    ) -> str:
        """
        אומדן ביצועים לשבוע הקרוב

        Returns:
            str: תיאור עברי של הצפוי
        """
        lines = ["📈 הערכה לשבוע הקרוב:", ""]

        # מזג אוויר
        if weather_forecast.get('is_rainy'):
            lines.append(f"  🌧️ {weather_forecast['description_he']} ({weather_forecast['precipitation_mm']}מ״מ)")
            lines.append("  → צפוי ירידה בביקורים, הפחת הזמנה ב-20%")
        else:
            lines.append(f"  {weather_forecast['description_he']}")
            lines.append("  → תנאים טובים למכירות")

        # חגים
        if holiday_factor > 1.0:
            lines.append(f"  ✡️ קרוב לחג - הזמנה מוגברת ב-{int((holiday_factor-1)*100)}%")
        elif holiday_factor < 1.0:
            lines.append(f"  ⚠️ תקופה קשה - צפוי ירידה ב-{int((1-holiday_factor)*100)}%")

        # מלאי
        total_items = sum(current_inventory.values())
        if total_items > 30:
            lines.append(f"  📦 מלאי גבוה ({total_items} יח') - אפשר להזמין פחות")
        elif total_items < 10:
            lines.append(f"  ⚠️ מלאי נמוך ({total_items} יח') - הזמן להזמין!")

        return "\n".join(lines)
