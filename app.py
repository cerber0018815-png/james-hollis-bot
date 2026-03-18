# app.py
import os
import threading
from flask import Flask
from bot import main as run_bot  # Импортируем вашу главную функцию из bot.py

app = Flask(__name__)

@app.route('/')
def index():
    return "Бот Джеймс Холлис работает!"

@app.route('/health')
def health():
    return "OK"

def start_bot():
    """Функция для запуска бота в отдельном потоке."""
    run_bot()

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    # Запускаем веб-сервер, который слушает порт, указанный Render
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))