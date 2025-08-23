import os
import time

import gspread
import pandas as pd
import schedule
import telebot
from dotenv import load_dotenv

load_dotenv()

from Autoresponder import Autoresponder

TELEBOT_TOKEN = os.getenv("TELEBOT_TOKEN")
bot = telebot.TeleBot(TELEBOT_TOKEN)

class Update:
    def __init__(self, key_table, name, wb_token):
        self.client = Autoresponder(key_table, name, wb_token)

    def start(self):
        print(f"[INFO] Start autoresponder for {self.client.name}")
        self.client.start_autoresponder()

def get_clients() -> pd.DataFrame:
    gc = gspread.service_account(filename="credentials.json")
    sh = gc.open_by_key("18L3gx1ps1p7fTHVCcte7tHjjW3PyLoJpD79TdMNkbOY")
    data = sh.worksheet("data").get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

def all_start_to_user():
    for i in range(3):
        try:
            df = get_clients()
            break
        except Exception as ex:
            bot.send_message("-1002417112074", f"[WARN] Clients haven't got \nError: {ex}")
            time.sleep(60)
    for row in df.itertuples():   # noqa
        if row.type == "Autoresponder":  # noqa
            if row.enabled == "1":   # noqa
                name = row.name  # noqa
                wb_token = row.wb_token  # noqa
                key_table = row.key_table  # noqa
                client = Update(key_table, name, wb_token)
                #for j in range(3):
                    # try:
                client.start()
                    #     bot.send_message("-1002417112074",f"✅GOOD SEND to USER\n name:{i.name}")
                    #     break
                    # except Exception as ex:
                    #     bot.send_message("-1002417112074",f"ERROR ERROR ERROR TO USER \nname:{i.name}\nError: {ex}")
                    #     time.sleep(120)

def main():
    all_start_to_user()
    schedule.every(5).minutes.do(all_start_to_user)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()