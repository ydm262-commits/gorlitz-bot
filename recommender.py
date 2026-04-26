"""
recommender.py - Smart Recommendation Engine for Gorlitz Bot
תפקיד: חישוב הזמנות מומלצות - Claude AI + fallback חישוב רגיל
"""

import os
import json
import logging
from typing import Dict, List, Optional
from database import get_database
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderRecommender:
    """מנוע מומלץ הזמנות חכם - Claude AI + rule-based fallback"""

    MINIMUM_ORDER_NIS = 500
    TWO_WEEK_PRODUCTS = ["רוגלך עלים קקאו", "קוקוש קייק"]

    @staticmethod
    def _get_claude_recommendation(
        products: list,
        inventory_left: Dict[str, int],
        recent_weeks: list,
        weather_factor: float,
        holiday_factor: float,
        holiday_desc: str,
        sales_pct: int
    ) -> Dict[str, int]:
        """קבל המלצה חכמה מ-Claude AI"""
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return {}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            products_info = "\n".join([
                f"- {p['name_he']}: קנייה ₪{p['buy_price']:.2f}, מכירה ₪{p['sell_price']:.2f}"
                for p in products
            ])
            if inventory_left:
                inventory_info = "\n".join([
                    f"- {name}: {qty} יחידות נשארו"
                    for name, qty in inventory_left.items() if qty > 0
                ]) or "- לא נשאר כלום"
            else:
                inventory_info = "- לא סופק מידע מלאי"
            if recent_weeks:
                history_lines = [
                    f"- {w.get('week_date','?')}: מכירות {w.get('sales_pct',0)}%, רווח ₪{w.get('net_profit',0):.0f} ({w.get('week_type','normal')})"
                    for w in recent_weeks[:5]
                ]
                history_info = "\n".join(history_lines)
            else:
                history_info = "- אין היסטוריה"
            weather_desc = "גשום" if weather_factor < 1.0 else "יפה"
            holiday_info = f"קרוב לחג: {holiday_desc} ({holiday_factor:.1f}x)" if holiday_desc else "שבוע רגיל"
            product_names = [p['name_he'] for p in products]
            example_json = {name: 5 for name in product_names[:3]}
            prompt = f"""אתה מנהל קניות מנוסה של מאפייה קטנה בבני ברק.
אתה צריך להחליט כמה להזמין מכל מוצר מספק גרליץ לשבוע הקרוב (לשישי).

📦 מוצרים ומחירים:
{products_info}

📊 מלאי שנשאר היום:
{inventory_info}

📅 היסטוריית 5 שבועות אחרונים:
{history_info}

🌤️ תנאים:
- מזג אוויר: {weather_desc}
- {holiday_info}
- אחוז מכירות: {sales_pct}%

📌 כללים:
1. הזמנה מינימלית: ₪{OrderRecommender.MINIMUM_ORDER_NIS}
2. {', '.join(OrderRecommender.TWO_WEEK_PRODUCTS)} - מחזיקים שבועיים, הזמן פחות
3. חלות ורוגלך שוקולד - נמכרים יותר
4. אל תזמין יותר מדי - חנות קטנה

ענה רק ב-JSON תקין, ללא הסבר:
{json.dumps(example_json, ensure_ascii=False)}

כלול את כל המוצרים. אם לא להזמין מוצר, שים 0."""
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = message.content[0].text.strip()
            if '{' in response_text:
                json_start = response_text.index('{')
                json_end = response_text.rindex('}') + 1
                result = json.loads(response_text[json_start:json_end])
                valid_names = {p['name_he'] for p in products}
                clean = {name: max(0, int(qty)) for name, qty in result.items() if name in valid_names}
                if clean:
                    logger.info(f"Claude recommendation: {clean}")
                    return clean
        except Exception as e:
            logger.warning(f"Claude API call failed: {e}")
        return {}

    @staticmethod
    def calculate_baseline_recommendation() -> Dict[str, int]:
        db = get_database()
        products = db.get_all_products()
        recent_weeks = db.get_recent_weeks(weeks=15)
        normal_weeks = [w for w in recent_weeks if w.get('week_type') == 'normal']
        avg_sales_pct = db.get_average_sales_pct()
        if normal_weeks:
            avg_sales_pct = sum(w['sales_pct'] for w in normal_weeks) / len(normal_weeks)
        avg_budget = 3500
        sales_factor = avg_sales_pct / 100
        baseline = {}
        for product in products:
            product_name = product['name_he']
            buy_price = product['buy_price']
            estimated_qty = int((avg_budget * sales_factor) / buy_price)
            baseline[product_name] = max(2, min(20, estimated_qty))
        return baseline

    @staticmethod
    def calculate_recommendation(
        inventory_left: Dict[str, int],
        weather_factor: float = 1.0,
        holiday_factor: float = 1.0,
        sales_pct: int = 70,
        holiday_desc: str = ""
    ) -> Dict[str, int]:
        """
        חישוב כמויות הזמנה מומלצות.
        מנסה Claude AI תחילה, ועובר ל-rule-based אם נכשל.
        """
        db = get_database()
        products = db.get_all_products()
        try:
            recent_weeks = db.get_recent_weeks(weeks=5)
            claude_recs = OrderRecommender._get_claude_recommendation(
                products, inventory_left, recent_weeks,
                weather_factor, holiday_factor, holiday_desc, sales_pct
            )
            if claude_recs:
                total_cost = sum(
                    claude_recs.get(p['name_he'], 0) * p['buy_price']
                    for p in products
                )
                if total_cost >= OrderRecommender.MINIMUM_ORDER_NIS:
                    return {k: v for k, v in claude_recs.items() if v > 0}
                logger.info(f"Claude total ₪{total_cost:.0f} below minimum, using rule-based")
        except Exception as e:
            logger.warning(f"Claude recommendation failed: {e}")
        logger.info("Using rule-based recommendation")
        baseline = OrderRecommender.calculate_baseline_recommendation()
        recommendations = {}
        for product in products:
            name = product['name_he']
            base_qty = baseline.get(name, 5)
            adjusted_qty = base_qty * weather_factor * holiday_factor * (sales_pct / 70)
            current_inventory = inventory_left.get(name, 0)
            qty_to_order = int(max(0, adjusted_qty - current_inventory))
            if qty_to_order > 0:
                qty_to_order = max(1, round(qty_to_order))
            recommendations[name] = qty_to_order
        total_cost = sum(
            recommendations[name] * db.get_product_by_name(name)['buy_price']
            for name in recommendations if recommendations[name] > 0
        )
        if total_cost < OrderRecommender.MINIMUM_ORDER_NIS:
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
        was_exceptional: bool = False,
        exceptional_reason: str = None
    ) -> Dict:
        avg_cost = 3500
        total_revenue = avg_cost * (sales_pct / 70) * 1.15
        waste_pct = int((100 - sales_pct) * 0.4) if sales_pct < 80 else 0
        waste_loss = (total_revenue / 100) * waste_pct
        net_profit = total_revenue - avg_cost - waste_loss
        return {
            "total_cost": round(avg_cost, 2),
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
        """עיצוב הודעת הזמנה ל-WhatsApp - טקסט נקי בעברית"""
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
        lines.extend(["", f"סה\"כ: {total_cost:.0f} ש\"ח"])
        if weather_desc:
            lines.append(f"מזג אוויר: {weather_desc}")
        if holiday_desc:
            lines.append(f"הערה: {holiday_desc}")
        lines.extend(["", "תודה רבה, יענקי!"])
        return "\n".join(lines)

    @staticmethod
    def estimate_next_week_performance(
        weather_forecast: Dict,
        holiday_factor: float,
        current_inventory: Dict[str, int]
    ) -> str:
        lines = ["הערכה לשבוע הקרוב:", ""]
        if weather_forecast.get('is_rainy'):
            lines.append(f"  גשם צפוי ({weather_forecast.get('precipitation_mm',0)}מ\"מ)")
            lines.append("  -> ירידה צפויה בביקורים, הפחת הזמנה ב-20%")
        else:
            lines.append(f"  {weather_forecast.get('description_he','מזג אוויר רגיל')}")
            lines.append("  -> תנאים טובים למכירות")
        if holiday_factor > 1.0:
            lines.append(f"  קרוב לחג - הזמנה מוגברת ב-{int((holiday_factor-1)*100)}%")
        elif holiday_factor < 1.0:
            lines.append(f"  תקופה קשה - ירידה ב-{int((1-holiday_factor)*100)}%")
        total_items = sum(current_inventory.values())
        if total_items > 30:
            lines.append(f"  מלאי גבוה ({total_items} יח') - אפשר להזמין פחות")
        elif total_items < 10:
            lines.append(f"  מלאי נמוך ({total_items} יח') - הזמן להזמין!")
        return "\n".join(lines)
