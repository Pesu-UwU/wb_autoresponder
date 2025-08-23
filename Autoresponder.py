import json
import os

import gspread
from gspread.utils import ValueInputOption
import pandas as pd
from typing import Dict, List

from dotenv import load_dotenv

import all_requests

load_dotenv()

GOOGLE_TABLE_KEY_DATA_OF_PATTERNS = os.getenv("GOOGLE_TABLE_KEY_DATA_OF_PATTERNS")


class Autoresponder:

    def __init__(self, key_table, name, wb_token):
        self.key_table = key_table
        self.name = name
        self.wb_token = wb_token
        self.gc = gspread.service_account(filename="credentials.json")
        self.sh = self.gc.open_by_key(key_table)

    def _get_feedbacks(self) -> pd.DataFrame:
        rows: List[Dict] = []

        take = 5000
        res = all_requests.get_feedbacks(self.wb_token, "true", take, 0).json()
        cnt_false = res["data"]["countUnanswered"]
        print(cnt_false)

        n = int((cnt_false + take - 1) / take)
        for coef in range(n):
            res = all_requests.get_feedbacks(self.wb_token, "false", take, coef * take).json()
            for fb in res["data"]["feedbacks"]:
                text = fb["text"]
                if text:
                    rows.append({
                        "id": fb["id"],
                        "text": text,
                        "date": fb["createdDate"],
                        "mark": fb["productValuation"],
                        "user_name": fb["userName"]
                    })
        return pd.DataFrame(rows, columns=["id", "text", "date", "mark", "user_name"])

    def _get_questions(self) -> pd.DataFrame:
        rows: List[Dict] = []

        take = 10000
        res = all_requests.get_questions(self.wb_token, "true", take, 0).json()
        cnt_false = res["data"]["countUnanswered"]
        print(cnt_false)

        n = int((cnt_false + take - 1) / take)
        for coef in range(n):
            res = all_requests.get_questions(self.wb_token, "false", take, coef * take).json()
            for q in res["data"]["questions"]:
                if q["state"] == "suppliersPortalSynch":  # только новые запросы без отклоненных
                    print(q["text"])
                    rows.append({
                        "id": q["id"],
                        "text": q["text"],
                        "date": q["createdDate"],
                    })
        return pd.DataFrame(rows, columns=["id", "text", "date"])


    def _compose_reply(self, obj) -> str: #  будет генериться с помощью api gpt
        reply = ""
        if hasattr(obj, "mark"):
            prompt = (f"Ты продавец товара на маркетплейсе Wildberries. Тебе нужно ответить на отзыв покупателя по следующим шаблонам. Ответы к положительным комментариям (оценка: больше или равна 4):"
                      f"[Добрый день! Спасибо, что нашли время для оценки нашего продукт. Ваши отзывы помогают улучшить качество заказов.\nС уважением, представители бренда!],"
                      f"[Здравствуйте, Надежда! Мы ценим и уважаем каждого клиента. Благодарим за положительный отзыв.\nС уважением, представители бренда!]."
                      f"Ответы к негативному отзыву: "
                      f"[Добрый день. Спешим к вам с извинениями!! Очень жаль, что покупка не смогла вас порадовать.\nС уважением, представители бренда!],"
                      f"[Здраствуйте, Марина! Благодарим Вас за обратную связь. Нам искренне жаль, что Вы разочарованы покупкой.\nС уважением, представители бренда!]."
                      f"Текст отзыва: {obj.text}, оценка отзыва: {obj.mark}, имя клиента: {obj.user_name}. Если у пользователя есть нормальное имя, то обратись к нему по имени. По необходимости можешь отойти от шаблона.")
            resp = all_requests.ask_gpt(prompt)
        else:
            sh = self.gc.open_by_key(GOOGLE_TABLE_KEY_DATA_OF_PATTERNS).worksheet("1 Вариант")
            data = json.dumps(sh.get_all_values(), ensure_ascii=False)

            prompt = (f"Ты продавец товара на маркетплейсе Wildberries. Тебе нужно ответить на отзыв покупателя по следующим шаблонам. Данные будут в виде JSON. "
                      f"Если отсутствует ответ на вопрос, значит верным ответом является последний встретившийся. Шаблоны: {data}. "
                      f"Если считаешь, что вопрос следует отклонить, верни строку REJECTED. При необходимости - импровизируй. "
                      f"Если считаешь, что ты не попал в суть вопроса с вероятностью 1/2, то в конце ответа поставь 2 символа *. Если не уверен, что стоит отклонить - не отклоняй."
                      f"Вот вопрос: {obj.text}")
            resp = all_requests.ask_gpt(prompt)

        data = resp.json()
        choices = data.get("choices")
        reply = choices[0]["message"]["content"] if (resp.ok and choices and choices[0]["message"].get("content")) else ""
        if not reply:
            print(f"[WARN] GPT empty reply: {data}")
            all_requests.debug_print_json(resp)
        return reply


    def _send_reply(self, obj, reply: str):
        if hasattr(obj, "mark"):
            resp = all_requests.send_reply_feedback(self.wb_token, obj.id, reply)
        else:
            state = "none" if reply == "REJECTED" else "wbRu"
            resp = all_requests.send_reply_question(self.wb_token, obj.id, reply, state)
        return resp.ok

    def _append_rows_bulk(self, name_sheet: str, rows: list[list]):
        ws = self.sh.worksheet(name_sheet)
        ws.append_rows(rows, value_input_option=ValueInputOption.raw)  # noqa

    def update_feedbacks(self):
        rows_to_write = []
        feedbacks = self._get_feedbacks()
        for fb in feedbacks.itertuples():
            reply = self._compose_reply(fb)
            if not reply:
                continue
            check = self._send_reply(fb, reply)
            if check:
                rows_to_write.append([fb.text, fb.date, fb.mark, reply])  # noqa
        if rows_to_write:
            self._append_rows_bulk("Отзывы", rows_to_write)


    def update_questions(self):
        rows_to_write = []
        questions = self._get_questions()
        for q in questions.itertuples():
            reply = self._compose_reply(q)
            if not reply:
                continue
            check = self._send_reply(q, reply)
            if check:
                rows_to_write.append([q.text, q.date, reply])  # noqa
        if rows_to_write:
            self._append_rows_bulk("Вопросы", rows_to_write)



    def start_autoresponder(self):
        self.update_feedbacks()
        self.update_questions()


