import os
import sys
import multiprocessing
import threading
from flask import Flask
from bot import main as run_bot

app = Flask(__name__)

@app.route('/')
def index():
    return "Бот Джеймс Холлис работает!"

@app.route('/health')
def health():
    # Проверка здоровья – можно всегда отвечать OK,
    # так как при падении бота процесс мониторинга завершит родителя.
    return "OK"

def start_bot_process():
    """Функция, выполняемая в дочернем процессе."""
    try:
        run_bot()
    except Exception as e:
        print(f"❌ Критическая ошибка в боте: {e}")
        sys.stdout.flush()
        sys.exit(1)  # Завершаем процесс с ошибкой

def monitor_process(proc):
    """Ожидает завершения дочернего процесса и завершает родителя."""
    proc.join()
    print("⚠️ Дочерний процесс бота завершился. Завершаем родительский процесс.")
    sys.stdout.flush()
    os._exit(1)  # Принудительное завершение родителя → Render перезапустит сервис

if __name__ == "__main__":
    # Запускаем бота в отдельном процессе (не в потоке)
    bot_process = multiprocessing.Process(target=start_bot_process, daemon=False)
    bot_process.start()

    # Поток для мониторинга дочернего процесса (демонический, чтобы не блокировать остановку)
    monitor_thread = threading.Thread(target=monitor_process, args=(bot_process,), daemon=True)
    monitor_thread.start()

    # Запускаем веб-сервер Flask на порту, указанном Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)