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
    return "OK"

def start_bot_process(env):
    """Функция, выполняемая в дочернем процессе. Принимает окружение как аргумент."""
    # Устанавливаем переданное окружение для дочернего процесса
    os.environ.update(env)
    try:
        print("🚀 Дочерний процесс бота запущен")
        print(f"TELEGRAM_TOKEN: {'установлен' if os.getenv('TELEGRAM_TOKEN') else 'НЕ УСТАНОВЛЕН'}")
        print(f"DEEPSEEK_API_KEY: {'установлен' if os.getenv('DEEPSEEK_API_KEY') else 'НЕ УСТАНОВЛЕН'}")
        print(f"PAYMENT_PROVIDER_TOKEN: {'установлен' if os.getenv('PAYMENT_PROVIDER_TOKEN') else 'НЕ УСТАНОВЛЕН'}")
        sys.stdout.flush()
        run_bot()
    except Exception as e:
        print(f"❌ Критическая ошибка в боте: {e}")
        sys.stdout.flush()
        sys.exit(1)

def monitor_process(proc):
    """Ожидает завершения дочернего процесса и завершает родителя."""
    proc.join()
    print("⚠️ Дочерний процесс бота завершился. Завершаем родительский процесс.")
    sys.stdout.flush()
    os._exit(1)

if __name__ == "__main__":
    # Явно копируем текущее окружение для передачи в дочерний процесс
    env = os.environ.copy()

    # Запускаем бота в отдельном процессе, передавая копию окружения
    bot_process = multiprocessing.Process(target=start_bot_process, args=(env,), daemon=False)
    bot_process.start()

    # Поток для мониторинга дочернего процесса (демонический, чтобы не блокировать остановку)
    monitor_thread = threading.Thread(target=monitor_process, args=(bot_process,), daemon=True)
    monitor_thread.start()

    # Запускаем веб-сервер Flask на порту, указанном Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
