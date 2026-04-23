"""
recommender.py - Smart Recommendation Engine for Gorlitz Bot
תפקיד: חישוב הזמנות מומלצות בהתאם לנתונים היסטוריים וגורמים חיצוניים
"""

from typing import Dict, List, Optional
from database import get_database
from datetime import datetime


class OrderRecommender:
    "" מנוע מומלץ הזמנות חכם"""

    MINIMUM_ORDER_NIS = 500
    TWO_WEEK_PRODUCTS = ["רוגלך עלים קקאו", "קוקוש קייק"]

    @staticmethod
    def calculate_baseline_recommendation() -> Dict[str, int]:
        db = get_database()
        products = db.get_all_products()
        recent_weeks = db.get_recent_weeks(weeks=15)
        normal_weeks = [w for w in recent_weeks if w.get('week_type') == 'normal']
        baseline = {}
        for product in products:
            product_name = product['name_he']
            buy_price = product['buy_price']
            avg_sales_pct = db.get_average_sales_pct() if hasattr(db, 'get_average_sales_pct') else 70
            if normal_weeks:
                avg_sales_pct = sum(w['sales_pct'] for w in normal_weeks) / len(normal_weeks)
            avg_budget = 3500
            sales_factor = avg_sales_pct / 100
            estimated_qty = int((avg_budget * sales_factor) / buy_price)
            estimated_qty = max(2, min(20, estimated_qty))
            baseline[product_name] = estimated_qty
        return baseline

    @staticmethod
    def calculate_recommendation(inventory_left, weather_factor=1.0, holiday_factor=1.0, sales_pct=70):
        db = get_database()
        products = db.get_all_products()
        baseline = OrderRecommender.calculate_baseline_recommendation()
        recommendations = {}
        for product in products:
            name = product['name_he']
            base_qty = baseline.get(name, 5)
            adjusted_qty = base_qty * weather_factor * holiday_factor * (sales_pct / 70)
            current_inventory = inventory_left.get(name, 0)
            qty_to_order = int(max(0, adjusted_qty - current_inventory))
            if qty_to_order > 0: qty_to_order = max(1, round(qty_to_order))
            recommendations[name] = qty_to_order
        return {k: v for k, v in recommendations.items() if v > 0}

    @staticmethod
    def calculate_weekly_summary(inventory_left, sales_pct=70, was_exceptional=False, exceptional_reason=None):
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
    def format_order_message(recommendations, week_date, summary, weather_desc="", holiday_desc=""):
        db = get_database()
        lines = ["🥖 הזמנה מ-גר\יץ", f"📅 לשבוע של {week_date}", "", "📦 הזמנה מומלצת:"]
        total_cost = 0
        for product_name, qty in sorted(recommendations.items()):
            if qty > 0:
                product = db.get_product_by_name(product_name)
                cost = qty * product['buy_price']
                total_cost += cost
                lines.append(f"  • {product_name}: {qty} יח' (₪{round(cost)})")
        lines.extend(["", f"📊", f"סה״ך הזמנה: ₪{round(total_cost)}", "", "יענקי, סזב �Pא נחדשה את המלאי!📱"])
        return "\n".join(lines)
