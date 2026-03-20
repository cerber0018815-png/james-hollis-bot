python
import os
import sys
import threading
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
    """Функция, выполняемая в потоке для запуска бота."""
    try:
        run_bot()
    except Exception as e:
        print(f"❌ Критическая ошибка в боте: {e}")
        sys.stdout.flush()
        # Принудительно завершаем процесс, чтобы Render перезапустил
        os._exit(1)

def monitor_thread(bot_thread):
    """Ожидает завершения потока бота и завершает процесс."""
    bot_thread.join()
    print("⚠️ Поток бота завершился. Завершаем процесс.")
    sys.stdout.flush()
    os._exit(1)

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot, daemon=False)
    bot_thread.start()

    # Мониторим поток бота
    monitor = threading.Thread(target=monitor_thread, args=(bot_thread,), daemon=True)
    monitor.start()

    # Запускаем Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
