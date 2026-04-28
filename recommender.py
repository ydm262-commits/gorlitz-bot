"""
recommender.py - Smart Recommendation Engine for Gorlitz Bot
תפקיד: חישוב הזמנות מומלצות בהתאם לנתונים היסטוריים וגורמים חיצוניים
משתמש ב-Claude AI לחשיבה חכמה, עם fallback חישובי
"""

import os
import json
from typing import Dict, List, Optional
from database import get_database
from datetime import datetime


class OrderRecommender:
    """מנוע מומלץ הזמנות חכם"""

    MINIMUM_ORDER_NIS = 500
    TWO_WEEK_PRODUCTS = ["רוגלך עלים קקאו", "קוקוש קייק"]

    # כמויות בסיס ריאליות לשבוע רגיל (calibrated לפי ניסיון)
    PRODUCT_DEFAULTS = {
        "חלות מתוק":            6,
        "רוגלך שוקולד":         10,
        "רוגלך עלים קקאו":      8,
        "קוקוש קייק":           5,
        "קראנץ' קקאו":          7,
        "גביניות":              6,
        "פס שמרים גבינה":       10,
        "פס שמרים קקאו שקית":   12,
        "פס שוקולד פירורים":    7,
    }

    @staticmethod
    def calculate_baseline_recommendation() -> Dict[str, int]:
        """
        כמות בסיסית לכל מוצר — מהנתונים ההיסטוריים ואחוז מכירות ממוצע.
        """
        db = get_database()
        products = db.get_all_products()

        recent_weeks = db.get_recent_weeks(weeks=15)
        normal_weeks = [w for w in recent_weeks if w.get('week_type') == 'normal']
        avg_sales_pct = db.get_average_sales_pct()
        if normal_weeks:
            avg_sales_pct = sum(w['sales_pct'] for w in normal_weeks) / len(normal_weeks)

        # מקדם מכירות יחסי לבסיס 80%
        sales_factor = avg_sales_pct / 80.0

        baseline = {}
        for product in products:
            name = product['name_he']
            base = OrderRecommender.PRODUCT_DEFAULTS.get(name, 6)
            qty = max(2, round(base * sales_factor))
            baseline[name] = qty

        return baseline

    @staticmethod
    def get_claude_recommendation(
        inventory_left: Dict[str, int],
        weather_factor: float,
        holiday_factor: float,
        sales_pct: int,
        weather_desc: str = "",
        holiday_desc: str = ""
    ) -> Optional[Dict[str, int]]:
        """
        שולח בקשה ל-Claude AI לקבל המלצת הזמנה חכמה.
        מחזיר None אם אין API key או אם קורה שגיאה.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None

        try:
            import anthropic
            db = get_database()
            products = db.get_all_products()
            recent_weeks = db.get_recent_weeks(50)  # כל ההיסטוריה

            # בנה הקשר
            products_info = "\n".join([
                f"- {p['name_he']}: עלות {p['buy_price']}₪, מכירה {p['sell_price']}₪"
                for p in products
            ])
            inventory_info = "\n".join([
                f"- {name}: נשאר {qty} יח'" for name, qty in inventory_left.items() if qty > 0
            ]) or "מלאי ריק — מכר הכל"

            # ניתוח מגמה מהיסטוריה
            normal_weeks = [w for w in recent_weeks if w.get('week_type') == 'normal']
            recent_3 = [w for w in recent_weeks[:3] if w.get('sales_pct', 0) > 0]
            recent_avg = sum(w.get('sales_pct', 0) for w in recent_3) / len(recent_3) if recent_3 else 65
            normal_avg = sum(w.get('sales_pct', 0) for w in normal_weeks) / len(normal_weeks) if normal_weeks else 65
            trend = "עולה" if recent_avg > normal_avg + 5 else ("יורד" if recent_avg < normal_avg - 5 else "יציב")

            history_info = "\n".join([
                f"- {w.get('week_date','')}: {w.get('week_type','')}, "
                f"{w.get('sales_pct',0)}% נמכר, "
                f"רווח {w.get('net_profit',0):.0f}₪"
                + (f", גשום" if w.get('weather_rain') else "")
                + (f", {w.get('holiday_type','')}" if w.get('holiday_type') else "")
                for w in recent_weeks
            ])

            context_parts = []
            if weather_desc:
                context_parts.append(f"מזג אוויר: {weather_desc}")
            if holiday_desc:
                context_parts.append(f"חג/מועד: {holiday_desc}")
            context_parts.append(f"אחוז מכירות שנשאר (מלאי קיים): {sales_pct}%")
            context_str = " | ".join(context_parts)

            prompt = f"""אתה מנהל הזמנות של חנות מאפה בבני ברק שמזמינה מגרליץ כל שבוע.

מוצרים ומחיריהם (מחיר קנייה | מחיר מכירה):
{products_info}

מה נשאר על המדף מהשבוע שעבר:
{inventory_info}

מצב השבוע הקרוב: {context_str}

כל היסטוריית המכירות ({len(recent_weeks)} שבועות):
{history_info}

מגמה: ממוצע שבועות רגילים = {normal_avg:.0f}% מכירות | ממוצע 3 שבועות אחרונים = {recent_avg:.0f}% | מגמה: {trend}

משימתך: על סמך ההיסטוריה האמיתית (מה הוצאו בשבועות דומים, כמה מכרו), החלט כמה להזמין מכל מוצר השבוע.

שיקולים:
- שבועות עם מכירות דומות לשבוע הנוכחי — מה הוצאו עליהם? זו נקודת ייחוס.
- מלאי שנשאר = כבר יש ממנו, הפחת מהכמות.
- גשם = ירידה של כ-20% בביקוש.
- לפני חג = עלייה בהתאם לחג.
- הזמנה מינימלית: 500₪.

ענה אך ורק ב-JSON תקין, ללא הסברים:
{{"שם_מוצר": כמות, ...}}"""

            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text.strip()
            # נקה JSON אם יש markdown
            if "```" in response_text:
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            recommendations = json.loads(response_text)
            # וודא שכל הערכים הם מספרים חיוביים
            return {k: max(0, int(v)) for k, v in recommendations.items() if v > 0}

        except Exception as e:
            print(f"Claude recommendation failed: {e}")
            return None

    @staticmethod
    def calculate_recommendation(
        inventory_left: Dict[str, int],
        weather_factor: float = 1.0,
        holiday_factor: float = 1.0,
        sales_pct: int = 70,
        holiday_desc: str = ""
    ) -> Dict[str, int]:
        """
        חישוב כמויות הזמנה מומלצות — Claude AI ראשון, fallback חישובי.
        """
        # נסה Claude AI קודם
        weather_desc = "גשום" if weather_factor < 1.0 else "יפה"
        claude_result = OrderRecommender.get_claude_recommendation(
            inventory_left=inventory_left,
            weather_factor=weather_factor,
            holiday_factor=holiday_factor,
            sales_pct=sales_pct,
            weather_desc=weather_desc,
            holiday_desc=holiday_desc
        )
        if claude_result:
            print(f"Using Claude AI recommendation")
            return claude_result

        # Fallback: חישוב חכם עם כמויות ריאליות
        print("Using rule-based recommendation (no Claude API key)")
        db = get_database()
        products = db.get_all_products()
        baseline = OrderRecommender.calculate_baseline_recommendation()
        recommendations = {}

        for product in products:
            name = product['name_he']
            base_qty = baseline.get(name, 5)

            # החל מקדמים
            adjusted = base_qty * weather_factor * holiday_factor
            adjusted *= (sales_pct / 70.0)

            # הפחת מלאי קיים
            current = inventory_left.get(name, 0)
            # מוצרים דו-שבועיים — הפחת פחות
            if name in OrderRecommender.TWO_WEEK_PRODUCTS:
                qty_to_order = max(0, round(adjusted - current * 0.5))
            else:
                qty_to_order = max(0, round(adjusted - current))

            recommendations[name] = qty_to_order

        # וודא מינימום 500₪
        total_cost = sum(
            recommendations[p['name_he']] * p['buy_price']
            for p in products
            if recommendations.get(p['name_he'], 0) > 0
        )
        if total_cost < OrderRecommender.MINIMUM_ORDER_NIS and total_cost > 0:
            shortage = OrderRecommender.MINIMUM_ORDER_NIS - total_cost
            for p in products:
                name = p['name_he']
                if recommendations.get(name, 0) > 0:
                    add = max(1, int(shortage / p['buy_price']))
                    recommendations[name] += add
                    shortage -= add * p['buy_price']
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
        """חישוב סיכום שבועי עם מחירים אמיתיים מ-DB"""
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

        net_profit = total_revenue - total_cost
        waste_pct = max(0, 100 - sales_pct)
        waste_loss = total_cost * (waste_pct / 100)

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
        """עיצוב הודעת הזמנה לWhatsApp"""
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

        lines.extend(["", "תודה רבה, יענקי!"])
        return "\n".join(lines)
