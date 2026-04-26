""" main.py - Entry point for Railway deployment
מפעיל את הבוט והאתר יחד על שרת אחד
"""
import os
import threading
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Initialize database once
from database import init_database
init_database()

def start_flask():
    """Run Flask web app in background thread"""
    from app import app
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting web app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Start Flask in background thread
flask_thread = threading.Thread(target=start_flask, daemon=True)
flask_thread.start()

# Run Telegram bot in main thread (required for signal handling)
token = os.getenv('TELEGRAM_BOT_TOKEN')
if not token:
    print("No TELEGRAM_BOT_TOKEN - bot disabled")
    import time
    while True:
        time.sleep(3600)
else:
    print("Starting Telegram bot...")
    try:
        from bot import main as bot_main
        asyncio.run(bot_main())
    except Exception as e:
        print(f"Bot error: {e}")
        import time
        while True:
            time.sleep(3600)
