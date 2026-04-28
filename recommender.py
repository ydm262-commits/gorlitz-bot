"""
recommender.py - Smart Recommendation Engine for Gorlitz Bot
תפקיד: חישוב הזמנות מומלצות בהתאם לנתונים היסטוריים וגורמים חיצוניים
משתמש ב-Claude AI לחשיבה חכמה, עם fallback חישובי
"""

import os
import json
import re
from typing import Dict, List, Optional
from database import get_database
from datetime import datetime


class OrderRecommender:
    """מנוע מומלץ הזמנות חכם"""

    MINIMUM_ORDER_NIS = 500
    # מוצרים שנזרקים תמיד בסוף שבוע (חיי מדף קצרים)
    ONE_WEEK_PRODUCTS = ["חלות מתוק", "גביניות", "פס שמרים גבינה"]
    # כל שאר המוצרים יכולים להחזיק לשבוע הבא
    TWO_WEEK_PRODUCTS = ["רוגלך שוקולד", "רוגלך עלים קקאו", "קוקוש קייק", "קראנץ' קקאו", "פס שמרים קקאו שקית", "פס שוקולד פירורים"]

    # כמויות בסיס ריאליות לשבוע רגיל (calibrated לפי ניסיון)
    PRODUCT_DEFAULTS = {
        "חלות מתוק":            0,
        "רוגלך שוקולד":         12,
        "רוגלך עלים קקאו":      3,
        "קוקוש קייק":           2,
        "קראנץ' קקאו":          2,
        "גביניות":              5,
        "פס שמרים גבינה":       2,
        "פס שמרים קקאו שקית":   3,
        "פס שוקולד פירורים":    2,
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
        holiday_desc: str = "",
        user_notes: str = ""
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
            weekly_summaries = db.get_recent_weeks(50)
            all_orders = db.get_recent_product_orders(weeks=30)

            products_info = "\n".join([
                f"- {p['name_he']}: עלות {p['buy_price']}₪, מכירה {p['sell_price']}₪"
                for p in products
            ])
            inventory_info = "\n".join([
                f"- {name}: נשאר {qty} יח'" for name, qty in inventory_left.items() if qty > 0
            ]) or "ריק — הכל נמכר"

            # טבלת הזמנות גולמית — כל 24 שבועות
            product_names = [p['name_he'] for p in products]
            header = "תאריך      | " + " | ".join([n[:6] for n in product_names]) + " | % מכירות | הערות"
            rows = []
            summary_by_date = {w['week_date']: w for w in weekly_summaries}
            for week in sorted(all_orders, key=lambda x: x['week_date']):
                date = week['week_date']
                qtys = [str(week['orders'].get(p, 0)) for p in product_names]
                summary = summary_by_date.get(date, {})
                sales = summary.get('sales_pct', '?')
                note = summary.get('week_type', '')
                if summary.get('weather_rain'):
                    note += ' גשם'
                if summary.get('holiday_type'):
                    note += f" {summary.get('holiday_type')}"
                if summary.get('user_notes'):
                    note += f" | 💬{summary.get('user_notes')}"
                rows.append(f"{date} | " + " | ".join(qtys) + f" | {sales}% | {note}")
            orders_table = header + "\n" + "\n".join(rows)

            context_parts = []
            if weather_desc:
                context_parts.append(f"מזג אוויר: {weather_desc}")
            if holiday_desc:
                context_parts.append(f"חג/מועד: {holiday_desc}")
            if sales_pct < 100:
                context_parts.append(f"נשאר מלאי — אחוז מכירות השבוע כ-{sales_pct}%")
            context_str = " | ".join(context_parts) if context_parts else "שבוע רגיל"

            user_notes_section = f"\nהערות מבעל החנות השבוע:\n{user_notes}\n" if user_notes else ""

            prompt = f"""אתה מנהל הזמנות של חנות מאפה בבני ברק שמזמינה ממאפיית גרליץ כל שבוע.

טבלת ההזמנות האמיתיות מ-24 השבועות האחרונים:
{orders_table}

מחירי קנייה:
{products_info}

מה נשאר על המדף עכשיו:
{inventory_info}

חוקי מלאי — חובה לפעול לפיהם בדיוק:
- חלות מתוק, גביניות, פס שמרים גבינה → נזרקים בסוף שבוע. אל תנכה את מה שנשאר — הזמן כמות מלאה לפי הממוצע ההיסטורי, כאילו המדף ריק.
- כל שאר המוצרים → מחזיקים שבועיים. הפחת את כל הכמות שנשארה מהכמות שהיית מזמין.

מצב: {context_str}
{user_notes_section}
הנחיות:
- התבסס בעיקר על 4-6 השבועות האחרונים בטבלה
- אם מוצר מופיע 0 בשבועות האחרונים — אל תזמין אותו
- אם צוין תקציב בהערות — ודא שהסכום הכולל (כמות × מחיר קנייה) לא עובר אותו
- ה-JSON חייב להכיל את הכמויות הסופיות אחרי כל התאמות

ענה בפורמט JSON בלבד:
{{
  "המלצות": {{"שם_מוצר": כמות, ...}},
  "הסבר": "משפט קצר על מה התבססת"
}}"""

            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            # לוג שימוש בטוקנים
            usage = message.usage
            input_tok = usage.input_tokens
            output_tok = usage.output_tokens
            cost_usd = (input_tok * 3 + output_tok * 15) / 1_000_000
            print(f"[Tokens] input={input_tok}, output={output_tok}, עלות≈${cost_usd:.4f}")

            response_text = message.content[0].text.strip()
            if "```" in response_text:
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            parsed = json.loads(response_text)
            # תמיכה בשני פורמטים — חדש עם הסבר, ישן בלי
            if "המלצות" in parsed:
                recommendations = parsed["המלצות"]
                OrderRecommender._last_reasoning = parsed.get("הסבר", "")
            else:
                recommendations = parsed
                OrderRecommender._last_reasoning = ""
            # וודא שכל הערכים הם מספרים חיוביים
            recommendations = {k: max(0, int(v)) for k, v in recommendations.items() if v > 0}

            # --- לולאת תיקון עצמי ---
            # חשב עלות אמיתית מ-DB
            db2 = get_database()
            actual_total = 0.0
            for pname, qty in recommendations.items():
                p = db2.get_product_by_name(pname)
                if p:
                    actual_total += qty * p['buy_price']

            # חפש תקציב בהערות המשתמש
            budget_limit = None
            if user_notes:
                m = re.search(r'תקציב[:\s]*(\d+)', user_notes)
                if not m:
                    m = re.search(r'(\d+)\s*[₪ש"ח]', user_notes)
                if m:
                    budget_limit = float(m.group(1))

            needs_correction = False
            correction_reason = ""

            if budget_limit and actual_total > budget_limit * 1.05:
                needs_correction = True
                correction_reason = (
                    f"סה\"כ בפועל: ₪{actual_total:.0f} — חורג מהתקציב שצוין ₪{budget_limit:.0f}. "
                    f"צמצם כמויות עד שהסכום ≤ ₪{budget_limit:.0f}."
                )
            elif budget_limit is None:
                # בדוק אם קלוד כתב בהסבר סכום שלא מתאים למציאות
                # קח את הסכום ה-אחרון שקלוד כתב — הוא הסופי אחרי תיקוניו
                all_amounts = re.findall(r'[≈=]\s*(\d+)\s*₪|₪\s*(\d+)', OrderRecommender._last_reasoning or "")
                claimed = None
                for a, b in reversed(all_amounts):
                    val = a or b
                    if val and int(val) > 100:  # סכום הגיוני (לא כמות)
                        claimed = float(val)
                        break
                if claimed and abs(claimed - actual_total) > claimed * 0.08:  # פער > 8%
                    needs_correction = True
                    correction_reason = (
                        f"כתבת בהסבר שהסכום הסופי הוא ₪{claimed:.0f} אבל ה-JSON שלך נותן ₪{actual_total:.0f}. "
                        f"תקן את כמויות ה-JSON כך שהחישוב יתן בדיוק את מה שכתבת."
                    )

            if needs_correction:
                print(f"[Self-correction] {correction_reason}")
                # בנה פירוט כמויות × מחירים לקלוד
                breakdown_lines = []
                for pname, qty in recommendations.items():
                    p = db2.get_product_by_name(pname)
                    price = p['buy_price'] if p else 0
                    breakdown_lines.append(f"  {pname}: {qty} × ₪{price} = ₪{qty*price:.0f}")
                breakdown = "\n".join(breakdown_lines)

                correction_prompt = f"""התשובה הקודמת שלך:
{json.dumps({"המלצות": recommendations, "הסבר": OrderRecommender._last_reasoning}, ensure_ascii=False)}

חישוב אמיתי של הסכום:
{breakdown}
סה"כ בפועל: ₪{actual_total:.0f}

{correction_reason}

ענה שוב בפורמט JSON בלבד:
{{
  "המלצות": {{"שם_מוצר": כמות, ...}},
  "הסבר": "..."
}}"""

                msg2 = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1000,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": correction_prompt}
                    ]
                )
                u2 = msg2.usage
                cost2 = (u2.input_tokens * 3 + u2.output_tokens * 15) / 1_000_000
                print(f"[Correction tokens] input={u2.input_tokens}, output={u2.output_tokens}, עלות≈${cost2:.4f}")

                r2 = msg2.content[0].text.strip()
                if "```" in r2:
                    r2 = r2.split("```")[1]
                    if r2.startswith("json"):
                        r2 = r2[4:]
                r2 = r2.strip()
                p2 = json.loads(r2)
                if "המלצות" in p2:
                    recommendations = {k: max(0, int(v)) for k, v in p2["המלצות"].items() if v > 0}
                    OrderRecommender._last_reasoning = p2.get("הסבר", "")
                else:
                    recommendations = {k: max(0, int(v)) for k, v in p2.items() if v > 0}

            return recommendations

        except Exception as e:
            print(f"Claude recommendation failed: {e}")
            return None

    @staticmethod
    def calculate_recommendation(
        inventory_left: Dict[str, int],
        weather_factor: float = 1.0,
        holiday_factor: float = 1.0,
        sales_pct: int = 70,
        holiday_desc: str = "",
        user_notes: str = ""
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
            holiday_desc=holiday_desc,
            user_notes=user_notes
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
            # מוצרים שנזרקים — לא מפחיתים (לא יהיו שם); מוצרים שמחזיקים — מפחיתים הכל
            if name in OrderRecommender.ONE_WEEK_PRODUCTS:
                qty_to_order = max(0, round(adjusted))  # לא מפחיתים — ייזרקו
            elif name in OrderRecommender.TWO_WEEK_PRODUCTS:
                qty_to_order = max(0, round(adjusted - current))  # מפחיתים הכל
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

        for product_name, qty in sorted(recommendations.items()):
            if qty > 0:
                lines.append(f"  {product_name}: {qty} יח'")

        if holiday_desc:
            lines.extend(["", f"הערה: {holiday_desc}"])

        lines.extend(["", "תודה רבה, יענקי!"])
        return "\n".join(lines)
