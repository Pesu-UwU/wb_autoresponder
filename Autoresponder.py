import datetime
import json
import os
import time

import gspread
from gspread.utils import ValueInputOption
import pandas as pd
from typing import Dict, List

from dotenv import load_dotenv

import all_requests

load_dotenv()

GOOGLE_TABLE_KEY_DATA_OF_PATTERNS = os.getenv("GOOGLE_TABLE_KEY_DATA_OF_PATTERNS")
ERROR_SLEEP_TIME = 60
MAX_RETRIES = 3


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
                total_text = ""
                text = fb["text"]  # комментарий
                pros = fb["pros"]  # преимущества
                cons = fb["cons"]  # недостатки
                bables = fb["bables"]  # теги
                if pros:
                    total_text += f"Преимущества: {pros}\n"
                if cons:
                    total_text += f"Недостатки: {cons}\n"
                if text:
                    total_text += f"Комментарий: {text}\n"
                if bables:
                    total_text += f"Теги: {bables}\n"
                if fb["photoLinks"] or fb["video"]:
                    total_text += "Приложены фото или видео\n"
                if total_text[-1] == "\n":
                    total_text = total_text[:-1]
                rows.append({
                    "id": fb["id"],
                    "text": total_text,
                    "date_fb": fb["createdDate"],
                    "mark": fb["productValuation"],
                    "user_name": fb["userName"],
                    "subject_name":  fb["subjectName"],
                    "nm_id": fb["productDetails"]["nmId"]
                })

        return pd.DataFrame(rows, columns=["id", "text", "date_fb", "mark", "user_name", "subject_name", "nm_id"])

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
                    print(q["text"])  #ВЫВОД
                    rows.append({
                        "id": q["id"],
                        "text": q["text"],
                        "date_q": q["createdDate"],
                    })
        return pd.DataFrame(rows, columns=["id", "text", "date_q"])

    def _get_char(self):
        char = Dict[str, Dict[str, str]]
        limit = 100
        nm_id = None
        updated_at = None
        while True:
            result = all_requests.get_cards(self.wb_token, limit, nm_id, updated_at).json()
            total_cnt = result["cursor"]["total"]
            if total_cnt == 0: break
            for card in result["cards"]:
                try:
                    char.update({"nm_id": {"subject_name": card["subjectName"], "title": card["title"], "description": card["description"]}})
                except Exception:
                    continue
            if total_cnt < limit:
                break
            nm_id = result["cursor"]["nmId"]
            updated_at = result["cursor"]["updatedAt"]
        all_requests.debug_print_dict(char)
        return char



    def _compose_reply(self, obj) -> str: #  будет генериться с помощью api gpt
        if hasattr(obj, "mark"):
            char = self._get_char()
            prompt = (f"Ты автоответчик продавца товара на маркетплейсе Wildberries. Тебе нужно ответить на отзыв покупателя следующим образом. Если в тексте указаны только теги, то ответь шаблонно. Ответ к положительным комментариям (оценка: больше или равна 4):"
                      f"[Здравствуйте, Надежда! Мы ценим и уважаем каждого клиента. Благодарим за положительный отзыв.\nС уважением, представители бренда!]."
                      f"Ответы к негативному отзыву: "
                      f"[Здраствуйте, Марина! Благодарим Вас за обратную связь. Нам искренне жаль, что Вы разочарованы покупкой.\nС уважением, представители бренда!]."
                      f"Отвечай на отзывы покупателей в их стиле (коротко/подробно, сухо/эмоционально), но всегда вежливо и делово. "
                      f"На негативные отзывы реагируй спокойно: поблагодари за обратную связь, дай нейтральный комментарий и предложи альтернативу. "
                      f"В каждом ответе в конце обязательно рекомендуй схожий товар из ассортимента. Для этого используй JSON со списком товаров. Найди в нем похожий товар (по типу и характеристикам: рукав, сезонность, материал и т.п.). "
                      f"Если нет точного совпадения, выбери ближайшую альтернативу. Артикул - это поле nm_id, название - title. Добавь рекомендацию в формате: «Рекомендуем также обратить внимание на нашу модель: [название] (артикул: XXXXX)». Данные бери из этого json: {char}"
                      f"Текст отзыва: {obj.text}, оценка отзыва: {obj.mark}, имя клиента: {obj.user_name}, артикул купленного товара (чтобы ты случайно не порекомендовал его же): {obj.nm_id}, тип товара: {obj.subject_name}"
                      f" Если у пользователя есть нормальное имя, то обратись к нему по имени. Избегай в своей речи взываний к дополнительным вопросам и слова")
            resp = all_requests.ask_gpt(prompt)
        else:
            sh = self.gc.open_by_key(GOOGLE_TABLE_KEY_DATA_OF_PATTERNS).worksheet("1 Вариант")
            data = json.dumps(sh.get_all_values(), ensure_ascii=False)

            prompt = (f"Ты автоответчик продавца товара на маркетплейсе Wildberries. Тебе нужно ответить на отзыв покупателя по следующим шаблонам. Данные будут в виде JSON. "
                      f"Если отсутствует ответ на вопрос, значит верным ответом является последний встретившийся. Шаблоны: {data}. "
                      f"Если считаешь, что вопрос следует отклонить, верни строку REJECTED. При необходимости - импровизируй. "
                      f"Если считаешь, что ты не попал в суть вопроса с вероятностью 1/2, то в конце ответа поставь 2 символа *. Если не уверен, что стоит отклонить - не отклоняй."
                      f"Вот вопрос: {obj.text}")
            resp = all_requests.ask_gpt(prompt)

        data = resp.json()
        reply = ""
        if resp.ok:
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                reply = choices[0].get("message", {}).get("content", "")
        if not reply:
            print(f"[WARN] GPT empty reply: {data}")
            all_requests.debug_print_json(resp)
        print(f"[GPT] reply: {reply}")
        return reply


    def _send_reply(self, obj, reply: str):
        if hasattr(obj, "mark"):
            resp = all_requests.send_reply_feedback(self.wb_token, obj.id, reply)
        else:
            state = "none" if reply == "REJECTED" else "wbRu"
            resp = all_requests.send_reply_question(self.wb_token, obj.id, reply, state)
        if resp.ok:
            print(f"[INFO] Sent reply for id={obj.id}")
        else:
            print(f"[WARN] Failed to send reply for id={obj.id}, status={resp.status_code}")
        return resp.ok

    def _append_rows_bulk(self, name_sheet: str, rows: list[list]):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                ws = self.sh.worksheet(name_sheet)
                ws.append_rows(rows, value_input_option=ValueInputOption.raw)  # noqa
                print(f"[INFO] Appended {len(rows)} rows to sheet '{name_sheet}' for {self.name}")
                break
            except Exception as ex:
                print(f"[WARN] Failed to append rows to sheet '{name_sheet}' for {self.name}: {ex}")
                time.sleep(ERROR_SLEEP_TIME)


    def update_feedbacks(self):
        rows_to_write = []
        feedbacks = self._get_feedbacks()
        i = 1
        for fb in feedbacks.itertuples():
            if i == 100 :
                break
            reply = self._compose_reply(fb)
            if not reply:
                continue
            date_ans = datetime.datetime.now()
            check = self._send_reply(fb, reply)
            if check:
                rows_to_write.append([fb.nm_id, fb.date_fb, fb.text, fb.mark, reply, date_ans])  # noqa
            i += 1
        if rows_to_write:
            self._append_rows_bulk("Отзывы", rows_to_write)


    def update_questions(self):
        rows_to_write = []
        questions = self._get_questions()
        for q in questions.itertuples():
            reply = self._compose_reply(q)
            exit(0)
            if not reply:
                continue
            check = self._send_reply(q, reply)
            if check:
                rows_to_write.append([q.text, q.date_q, reply])  # noqa
        if rows_to_write:
            self._append_rows_bulk("Вопросы", rows_to_write)



    def start_autoresponder(self):
        char = self._get_char()
        exit(0)
        self.update_feedbacks()
        #self.update_questions()


