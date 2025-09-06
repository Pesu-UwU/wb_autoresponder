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
        self.characteristics = {}

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
                    "nm_id": fb["productDetails"]["nmId"],
                    "supplier_article": fb["productDetails"]["supplierArticle"]
                })

        return pd.DataFrame(rows, columns=["id", "text", "date_fb", "mark", "user_name", "subject_name", "nm_id", "supplier_article"])

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

    def _get_characteristics(self):
        characteristics: Dict[str, Dict[str, str]] = {}
        limit = 100
        nm_id = None
        updated_at = None
        while True:
            result = all_requests.get_cards(self.wb_token, limit, nm_id, updated_at)
            #all_requests.debug_print_json(result)
            result=result.json()
            total_cnt = result["cursor"]["total"]
            if total_cnt == 0: break
            for card in result["cards"]:
                nm_id = card["nmID"]
                characteristics.update({nm_id: {"subject_name": card["subjectName"], "title": card["title"]}})
                for characteristic in card["characteristics"]:
                    characteristics[nm_id].update({characteristic["name"]: characteristic["value"]})
            if total_cnt < limit:
                break
            nm_id = result["cursor"]["nmID"]
            updated_at = result["cursor"]["updatedAt"]
        #all_requests.debug_print_dict(characteristics)
        return characteristics



    def _compose_reply(self, obj) -> str: #  будет генериться с помощью api gpt
        if hasattr(obj, "mark"):
            prompt = (f"""Ты — живой, человечный и немного ироничный ассистент бренда Wildberries. Ты отвечаешь на отзывы покупателей с маркетплейса (например, Wildberries). Твоя задача — создать по-настоящему живой, искренний, не шаблонный ответ на каждый отзыв. 
            Тебе передаются: - {obj.text} — текст отзыва (возможно с тегами) - {obj.mark} — оценка (от 1 до 5) - {obj.user_name} — имя клиента - {obj.subject_name} — название основного товара (например, «Пижама») - {obj.nm_id} — артикул товара, о котором оставлен отзыв - {json.dumps(self.characteristics, ensure_ascii=False)} — словарь всех остальных наших товаров, в формате: {{ "456789": {{"title": "Шарф «Лесная дымка»", "color": "светло-серый", "subject_name": "Шарф",  }},  ... }} Твоя задача: 1. Ответить на отзыв (исходя из оценки и текста) — с человечностью, юмором, сочувствием или радостью. 2. Обязательно вставь рекомендацию одного из других товаров из characteristics. Выбери его так, чтобы он логично дополнял или мог заменить основной товар. 3. Упомяни: - Название рекомендованного товара; - Коротко, зачем он может подойти (в контексте отзыва); - Упомяни его артикул (nm_id); - Не пиши «у нас есть» — пиши, как будто это совет от друга: «А вот, кстати, есть вещь, которая может классно зайти — это ___, арт. ___». Важно: - Не используй шаблонов. Каждый ответ должен быть уникальным по структуре и стилю. - Если отзыв негативный — не оправдывайся, поблагодари за честность, посочувствуй, предложи альтернативу. - Если отзыв позитивный — порадоваться вместе, можно пошутить, добавить рекомендацию как бонус. - В рекомендацию обязательно вплети артикул: «арт. 456789» — но деликатно. - Не используй сухих фраз вроде «рекомендуем вам посмотреть». Примеры рекомендаций: - «Кстати, есть ещё шарф «Лесная дымка» (арт. 456789) — он такой уютный, что даже плохое настроение не пристаёт.» - «Если хочется чего-то потеплее — присмотритесь к комплекту с артикулом 987654. Он объятие, а не пижама.» - «Есть, между прочим, ещё одна находка — шарф “Пыльная роза” (арт. 112233). Может идеально дополнить ваш стиль.» Пиши от лица бренда Wildberries, как будто ты человек, а не бот. Будь стильным, лёгким, тёплым. И не забывай об артикуле рекомендованного товара.""")
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
        print(f"[GPT] given text: {obj.text}")
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
        i = 0
        for fb in feedbacks.itertuples():
            if i == 10:
                break
            reply = self._compose_reply(fb)
            #exit(0)
            if not reply:
                continue
            date_ans = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            #check = self._send_reply(fb, reply)
            # if check:
            #     rows_to_write.append([fb.supplier_article, fb.date_fb, fb.mark, fb.text, reply, date_ans])  # noqa
            rows_to_write.append([fb.supplier_article, fb.date_fb, fb.mark, fb.text, reply, date_ans])  # noqa
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
        #all_requests.debug_print_json(all_requests.get_cards_trash(self.wb_token, 100))
        self.characteristics = self._get_characteristics()
        #exit(0)
        #all_requests.debug_print_dict(self.characteristics)
        self.update_feedbacks()
        #self.update_questions()


