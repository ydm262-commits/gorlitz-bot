"""
app.py - Flask Web App for Gorlitz Orders
אתר הזמנות גרליץ - מסונכרן עם הבוט
"""

import os
import asyncio
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'gorlitz-secret-2024')

GORLITZ_WHATSAPP = os.getenv('GORLITZ_WHATSAPP', '972505603600')
LOGIN_CODE = os.getenv('LOGIN_CODE', '1234')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def get_db():
    from database import get_database
    return get_database()


def run_async(coro):
    """Run async function in sync context - Python 3.12 safe"""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    error = None
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if code == LOGIN_CODE:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'קוד שגוי, נסה שוב'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/')
@login_required
def index():
    db = get_db()
    products = db.get_all_products()
    return render_template('index.html', products=products)


@app.route('/api/products')
@login_required
def api_products():
    db = get_db()
    return jsonify(db.get_all_products())


@app.route('/api/analyze', methods=['POST'])
@login_required
def api_analyze():
    from recommender import OrderRecommender
    from weather import WeatherClient
    from jewish_calendar import JewishCalendar

    data = request.get_json()
    inventory = data.get('inventory', {})
    user_notes = data.get('user_notes', '')

    # Get weather and calendar
    try:
        weather = run_async(WeatherClient.get_friday_forecast())
        calendar = JewishCalendar()
        holiday_factor, holiday_desc = run_async(calendar.get_holiday_factor())
    except Exception:
        weather = {'is_rainy': False, 'description_he': ''}
        holiday_factor, holiday_desc = 1.0, ''

    weather_factor = 0.80 if weather.get('is_rainy') else 1.0
    total_items = sum(inventory.values())
    # 0 נשאר = 100% מכירות, 10 נשאר = 70%, 20 נשאר = 40%
    sales_pct = max(40, min(100, 100 - total_items * 3))

    recommendations = OrderRecommender.calculate_recommendation(
        inventory,
        weather_factor=weather_factor,
        holiday_factor=holiday_factor,
        sales_pct=sales_pct,
        holiday_desc=holiday_desc,
        user_notes=user_notes
    )

    summary = OrderRecommender.calculate_weekly_summary(
        inventory, sales_pct=sales_pct, recommendations=recommendations
    )

    db = get_db()
    total_cost = 0
    order_items = []
    for product_name, qty in sorted(recommendations.items()):
        if qty > 0:
            product = db.get_product_by_name(product_name)
            cost = qty * product['buy_price']
            total_cost += cost
            order_items.append({
                'name': product_name,
                'qty': qty,
                'cost': round(cost, 2),
                'buy_price': product['buy_price']
            })

    reasoning = getattr(OrderRecommender, '_last_reasoning', '')

    return jsonify({
        'recommendations': recommendations,
        'order_items': order_items,
        'total_cost': round(total_cost, 2),
        'summary': summary,
        'weather': weather,
        'holiday_desc': holiday_desc,
        'sales_pct': sales_pct,
        'ai_reasoning': reasoning,
        'context': {
            'weather_desc': weather.get('description_he', ''),
            'is_rainy': weather.get('is_rainy', False),
            'holiday_desc': holiday_desc,
            'sales_pct': sales_pct
        }
    })


@app.route('/api/history')
@login_required
def api_history():
    db = get_db()
    weeks = db.get_recent_weeks(10)
    return jsonify(weeks)


@app.route('/api/whatsapp-message', methods=['POST'])
@login_required
def api_whatsapp():
    """
    Return the WhatsApp message TEXT (unencoded).
    The frontend will encode it using encodeURIComponent for correct UTF-8 handling.
    """
    from recommender import OrderRecommender

    data = request.get_json()
    recommendations = data.get('recommendations', {})
    week_date = data.get('week_date', datetime.now().strftime('%Y-%m-%d'))
    summary = data.get('summary', {})
    weather_desc = data.get('weather_desc', '')
    holiday_desc = data.get('holiday_desc', '')

    message = OrderRecommender.format_order_message(
        recommendations, week_date, summary, weather_desc, holiday_desc
    )

    # Return the raw message text - let JavaScript encode it correctly
    return jsonify({
        'message': message,
        'phone': GORLITZ_WHATSAPP
    })


@app.route('/api/save-order', methods=['POST'])
@login_required
def api_save_order():
    db = get_db()
    data = request.get_json()
    week_date = data.get('week_date', datetime.now().strftime('%Y-%m-%d'))
    summary_data = data.get('summary', {})
    user_notes = data.get('user_notes', '')
    db.save_weekly_summary(week_date, summary_data, user_notes=user_notes)
    return jsonify({'success': True})


@app.route('/api/sync-sheet', methods=['POST'])
@login_required
def api_sync_sheet():
    """סנכרון נתונים מגוגל שיטס"""
    from sheets_sync import sync_from_google_sheets
    result = sync_from_google_sheets()
    return jsonify(result)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
