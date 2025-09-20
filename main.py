import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict

import gspread
import pandas as pd
import schedule
import telebot
from dotenv import load_dotenv

from Autoresponder import Autoresponder

import logging
import sys

# Настройка логов один раз в main.py (или в entrypoint)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


load_dotenv()

TELEBOT_TOKEN = os.getenv("TELEBOT_TOKEN")
TABLE_DATA = os.getenv("TABLE_DATA")  # ключ гугл-таблицы с клиентами
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "6"))          # верхняя граница параллельных клиентов
CLIENT_RETRIES = int(os.getenv("CLIENT_RETRIES", "3"))    # ретраи на клиента
RETRY_SLEEP_SEC = int(os.getenv("RETRY_SLEEP_SEC", "300"))
SCHEDULE_SECONDS = int(os.getenv("SCHEDULE_SECONDS", "30"))  # тик планировщика

bot = telebot.TeleBot(TELEBOT_TOKEN)

# Постоянный пул воркеров (живёт всё время программы)
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="client")

# Таблица «кто сейчас выполняется»: key -> Future
_running: Dict[str, Future] = {}
_running_lock = threading.Lock()

# Чтобы не накладывались одновременные тики добавления задач
_tick_lock = threading.Lock()


class Update:
    def __init__(self, key_table: str, name: str, wb_token: str):
        self.client = Autoresponder(key_table, name, wb_token)

    def start(self):
        #print(f"[INFO] Start autoresponder for {self.client.name}")
        self.client.start_autoresponder()


def get_clients() -> pd.DataFrame:
    """Читает таблицу клиентов (лист 'data') и возвращает DataFrame."""
    gc = gspread.service_account(filename="credentials.json")
    sh = gc.open_by_key(TABLE_DATA)
    data = sh.worksheet("data").get_all_values()
    if not data or len(data) < 2:
        return pd.DataFrame(columns=["type", "enabled", "name", "wb_token", "key_table"])
    return pd.DataFrame(data[1:], columns=data[0])


def _client_key(name: str, key_table: str) -> str:
    """Уникальный ключ клиента, чтобы не запускать дубли."""
    return f"{name}::{key_table}"


def _on_done(client_key: str):
    """Коллбек: удалить клиента из _running по завершении задачи."""
    with _running_lock:
        _running.pop(client_key, None)
    print(f"[INFO] done: {client_key}")


def _run_client_task(key_table: str, name: str, wb_token: str):
    """Задача для пула: ретраи + запуск клиента."""
    # небольшой джиттер, чтобы разнести API-запросы
    time.sleep(random.uniform(0, 1.5))
    for attempt in range(1, CLIENT_RETRIES + 1):
        try:
            updater = Update(key_table, name, wb_token)
            updater.start()
            return
        except Exception as ex:
            msg = f"ERROR AUTORESPONDER name:{name} try:{attempt}/{CLIENT_RETRIES} Error: {ex}"
            logger.exception(msg)  # тут автоматически добавит traceback
            # try:
            #     bot.send_message("-1002417112074", msg)
            # except Exception:
            #     logger.warning("Failed to send error message to Telegram", exc_info=True)
            if attempt < CLIENT_RETRIES:
                time.sleep(RETRY_SLEEP_SEC)


def all_start_to_user():
    """Каждый тик: прочитать список клиентов и ДОБАВИТЬ в пул только тех, кто ещё не бежит."""
    with _tick_lock:
        # получаем клиентов с несколькими попытками
        df = None
        for i in range(3):
            try:
                df = get_clients()
                break
            except Exception as ex:
                warn = f"[WARN] Clients haven't got\nError: {ex}"
                print(warn)
                try:
                    bot.send_message("-1002417112074", warn)
                except Exception:
                    pass
                time.sleep(60)
        if df is None:
            return

        enabled = [
            r for r in df.itertuples()
            if getattr(r, "type", "") == "Autoresponder" and getattr(r, "enabled", "") == "1"
        ]
        if not enabled:
            print("[INFO] No enabled Autoresponder clients")
            return

        added = 0
        with _running_lock:
            # почистим «зомби» (на случай, если future завершился без коллбэка)
            dead = [k for k, f in _running.items() if f.done()]
            for k in dead:
                _running.pop(k, None)

            # добавим только тех, кто ещё не выполняется
            for r in enabled:
                key = _client_key(r.name, r.key_table)
                if key in _running:
                    continue  # уже бежит
                # отправляем в пул новую задачу
                fut = _executor.submit(_run_client_task, r.key_table, r.name, r.wb_token)
                # привяжем снятие с учёта по завершении
                fut.add_done_callback(lambda f, k=key: _on_done(k))
                _running[key] = fut
                added += 1

        print(f"[INFO] tick: enabled={len(enabled)}, running={len(_running)}, added_now={added}")


def main():
    # Первый прогон сразу
    all_start_to_user()

    # Планировщик: каждые SCHEDULE_SECONDS
    schedule.every(SCHEDULE_SECONDS).seconds.do(all_start_to_user)
    print(f"[INFO] scheduler started: every {SCHEDULE_SECONDS} second(s), MAX_WORKERS={MAX_WORKERS}")

    try:
        while True:
            schedule.run_pending()
            time.sleep(0.2)
    finally:
        # аккуратное завершение пула при остановке процесса
        _executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
