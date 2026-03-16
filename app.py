import os
import sys
import multiprocessing
from flask import Flask

# Импортируем функцию main из bot.py
from bot import main as run_bot

app = Flask(__name__)

@app.route('/')
def index():
    return "Бот Джеймс Холлис работает!"

@app.route('/health')
def health():
    return "OK"

def start_bot_process():
    """Запускает бота в отдельном процессе."""
    print("🔄 Запускаю бота в отдельном процессе...")
    try:
        run_bot()
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Запускаем бота в отдельном процессе (не в потоке!)
    bot_process = multiprocessing.Process(target=start_bot_process, daemon=True)
    bot_process.start()
    print(f"✅ Бот запущен в процессе с PID: {bot_process.pid}")
    
    # Запускаем веб-сервер Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Запускаем Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
