import time

import gspread
import pandas as pd
import schedule

from autoresponder import autoresponder


class update:
    def __init__(self, key_table, name, wb_token):
        self.client = autoresponder(key_table, name, wb_token)

    def start(self):
        print(f"Start {self.client.name}")
        self.client.start_autoresponder()

def all_start_to_user():
    gc = gspread.service_account(filename="credentials.json")
    sh = gc.open_by_key("18L3gx1ps1p7fTHVCcte7tHjjW3PyLoJpD79TdMNkbOY")
    data = sh.worksheet("data").get_all_values()
    print(data)
    df = pd.DataFrame(data[1:], columns=data[0])
    print(df)
    for row in df.itertuples():
        if row.type == "Autoresponder":
            if row.enabled == "1":
                name = row.name
                wb_token = row.wb_token
                key_table = row.key_table
                client = update(key_table, name, wb_token)
                #for j in range(3):
                    # try:
                client.start()
                    #     bot.send_message("-1002417112074",f"✅GOOD SEND to USER\n name:{i.name}")
                    #     break
                    # except Exception as ex:
                    #     bot.send_message("-1002417112074",f"ERROR ERROR ERROR TO USER \nname:{i.name}\nError: {ex}")
                    #     time.sleep(120)

def main():
    schedule.every(30).seconds.do(all_start_to_user)  #
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()