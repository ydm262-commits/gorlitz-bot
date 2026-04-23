"""
app.py - Flask Web App for Gorlitz Orders
אתר הזמנות גרליץ - מסונכרן עם הבוט
"""

import os
import asyncio
import urllib.parse
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
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed(): raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


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
    try:
        weather = run_async(WeatherClient.get_friday_forecast())
        calendar = JewishCalendar()
        holiday_factor, holiday_desc = run_async(calendar.get_holiday_factor())
    except Exception:
        weather = {'is_rainy': False, 'description_he': ''}
        holiday_factor, holiday_desc = 1.0, ''
    weather_factor = 0.80 if weather.get('is_rainy') else 1.0
    total_items = sum(inventory.values())
    sales_pct = max(50, min(100, int(70 + (total_items - 10) * 2)))
    recommendations = OrderRecommender.calculate_recommendation(inventory, weather_factor=weather_factor, holiday_factor=holiday_factor, sales_pct=sales_pct)
    summary = OrderRecommender.calculate_weekly_summary(inventory, sales_pct=sales_pct)
    db = get_db()
    total_cost = 0
    order_items = []
    for product_name, qty in sorted(recommendations.items()):
        if qty > 0:
            product = db.get_product_by_name(product_name)
            cost = qty * product['buy_price']
            total_cost += cost
            order_items.append({'name': product_name, 'qty': qty, 'cost': round(cost, 2), 'buy_price': product['buy_price']})
    return jsonify({'recommendations': recommendations, 'order_items': order_items, 'total_cost': round(total_cost, 2), 'summary': summary, 'weather': weather, 'holiday_desc': holiday_desc, 'sales_pct': sales_pct})


@app.route('/api/history')
@login_required
def api_history():
    db = get_db()
    return jsonify()

@app.route('/api/whatsapp-url', methods=['POST'])
@login_required
def api_whatsapp():
    from recommender import OrderRecommender
    data = request.get_json()
    recommendations = data.get('recommendations', {})
    week_date = data.get('week_date', datetime.now().strftime('%Y-%m-%d'))
    summary = data.get('summary', {})
    weather_desc = data.get('weather_desc', '')
    holiday_desc = data.get('holiday_desc', '')
    message = OrderRecommender.format_order_message(recommendations, week_date, summary, weather_desc, holiday_desc)
    encoded = urllib.parse.quote(message)
    url = f"https://wa.me/{GORLITZ_WHATSAPP}?text={encoded}"
    return jsonify({'url': url})


@app.route('/api/save-order', methods=['POST'])
@login_required
def api_save_order():
    db = get_db()
    data = request.get_json()
    week_date = data.get('week_date', datetime.now().strftime('%Y-%m-%d'))
    summary_data = data.get('summary', {})
    db.save_weekly_summary(week_date, summary_data)
    return jsonify({'success': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
