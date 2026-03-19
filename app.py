import os
import threading
import sys
from flask import Flask
from bot import main as run_bot

app = Flask(__name__)

@app.route('/')
def index():
    return "Бот Джеймс Холлис работает!"

@app.route('/health')
def health():
    return "OK"

def start_bot():
    try:
        run_bot()
    except Exception as e:
        # Логируем ошибку и принудительно завершаем процесс
        print(f"❌ Критическая ошибка в боте: {e}")
        sys.stdout.flush()  # гарантируем вывод лога
        os._exit(1)          # немедленное завершение с кодом ошибки

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке (daemon=True – для автоматического завершения при остановке Flask)
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    # Запускаем веб-сервер на порту, указанном Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
