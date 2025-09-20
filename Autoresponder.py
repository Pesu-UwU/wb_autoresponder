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
        self.gc = gspread.service_account(filename="service-credentials.json")
        self.sh = self.gc.open_by_key(key_table)
        self.characteristics = {}

    def _get_feedbacks(self) -> pd.DataFrame:
        rows: List[Dict] = []

        take = 5000
        res = all_requests.get_feedbacks(self.wb_token, "true", take, 0, name=self.name)
        if res is None or not res.ok:
            print(f"[WARN][{self.name}] get_feedbacks failed")
            return pd.DataFrame(columns=["id", "text", "date_fb", "mark", "user_name", "subject_name", "nm_id", "supplier_article"])
        res = res.json()
        cnt_false = res["data"]["countUnanswered"]
        print(f"[INFO][{self.name}] unanswered feedbacks: {cnt_false}")

        # Если нужна пагинация — можно пройтись циклами по skip
        res = all_requests.get_feedbacks(self.wb_token, "true", take, 0, name=self.name).json()
        for fb in res["data"]["feedbacks"]:
            total_text = ""
            text = fb.get("text")
            pros = fb.get("pros")
            cons = fb.get("cons")
            bables = fb.get("bables")
            if pros:
                total_text += f"Преимущества: {pros}\n"
            if cons:
                total_text += f"Недостатки: {cons}\n"
            if text:
                total_text += f"Комментарий: {text}\n"
            if bables:
                total_text += f"Теги: {bables}\n"
            if fb.get("photoLinks") or fb.get("video"):
                total_text += "Приложены фото или видео\n"
            if total_text.endswith("\n"):
                total_text = total_text[:-1]
            rows.append({
                "id": fb["id"],
                "text": total_text,
                "date_fb": fb["createdDate"],
                "mark": fb["productValuation"],
                "user_name": fb["userName"],
                "subject_name": fb["subjectName"],
                "nm_id": fb["productDetails"]["nmId"],
                "supplier_article": fb["productDetails"]["supplierArticle"]
            })

        return pd.DataFrame(rows, columns=["id", "text", "date_fb", "mark", "user_name", "subject_name", "nm_id", "supplier_article"])

    def _get_questions(self) -> pd.DataFrame:
        rows: List[Dict] = []

        take = 10000
        res = all_requests.get_questions(self.wb_token, "true", take, 0, name=self.name)
        if res is None or not res.ok:
            print(f"[WARN][{self.name}] get_questions failed")
            return pd.DataFrame(columns=["id", "text", "date_q"])
        res = res.json()
        cnt_false = res["data"]["countUnanswered"]
        print(f"[INFO][{self.name}] unanswered questions: {cnt_false}")

        n = int((cnt_false + take - 1) / take) if cnt_false else 0
        for coef in range(n or 1):
            res = all_requests.get_questions(self.wb_token, "false", take, coef * take, name=self.name).json()
            for q in res["data"].get("questions", []):
                if q["state"] == "suppliersPortalSynch":  # только новые запросы без отклоненных
                    print(f"[{self.name}] question: {q['text']}")
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
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")

        while True:
            resp = all_requests.get_cards(self.wb_token, limit, nm_id, updated_at, name=self.name)
            if resp is None or not resp.ok:
                print(f"[WARN][{self.name}] get_cards failed")
                break
            result = resp.json()
            total_cnt = result.get("cursor", {}).get("total", 0)
            if total_cnt == 0:
                break
            for card in result.get("cards", []):
                if card.get("updatedAt", "")[:10] <= cutoff:
                    continue
                nm_id = card.get("nmID")
                if not nm_id:
                    continue
                characteristics.setdefault(nm_id, {
                    "subject_name": card.get("subjectName", ""),
                    "title": card.get("title", "")
                })
                for ch in card.get("characteristics", []):
                    name, value = ch.get("name"), ch.get("value")
                    if name:
                        characteristics[nm_id][name] = value
            if total_cnt < limit:
                break
            nm_id = result["cursor"].get("nmID")
            updated_at = result["cursor"].get("updatedAt")
        return characteristics

    def _compose_reply(self, obj) -> str:
        """Генерация ответа. Без каких-либо маркеров/AI-META."""
        if hasattr(obj, "mark"):
            prompt = (f"""
            Ты — живой, человечный и немного ироничный представитель бренда, который продаёт товары на маркетплейсе. 
            Ты отвечаешь на отзывы покупателей.

            ВХОД:
            - text={obj.text} — текст отзыва (НЕ цитируй и НЕ пересказывай его в ответе).  
            - mark={obj.mark} — оценка 1–5.  
            - user_name={obj.user_name} — имя клиента (может быть пустым/странным).  
            - subject_name={obj.subject_name} — название основного товара.  
            - nm_id={obj.nm_id} — артикул основного товара.  
            - characteristics={json.dumps(self.characteristics, ensure_ascii=False)} — словарь других наших товаров вида:
            {{Артикул: {{Название характеристики: значение характеристики, ...}} }}   

            ЦЕЛЬ:
            - Дать искренний, дружеский, НЕ шаблонный ответ от лица представителя бренда.  
            - В тональности:  
              • 4–5★ — радость, лёгкий юмор, благодарность.  
              • 3★ — спокойный, нейтральный, с уважением к мнению.  
              • 1–2★ — тактичное участие и деликатная альтернатива, без оправданий и «товар не оправдал ожиданий».  

            ЖЁСТКИЕ ЗАПРЕТЫ:
            - Нельзя вставлять текст отзыва или метаданные (Оценка, Товар, Теги и пр.).  
            - Никаких фраз, которые подрывают бренд.  
            - Не упоминать возвраты, доставку, логику WB. Только про товар и эмоции.  

            СТИЛЬ:
            - Общение только на «вы».  
            - Приветствие с именем, если оно адекватное. Если имя пустое или странное — пишем без него («Здравствуйте!»).  
            - Тёплый, человечный тон. Макс. 2 эмодзи при уместности.  
            - 3–7 предложений, 350–800 знаков.  

            РЕКОМЕНДАЦИЯ:
            - Обязательно предложи один другой товар из characteristics (не тот же nm_id):  
              • логично дополняющий или заменяющий текущий;  
              • упомяни название и «арт. XXXXXXX»;  
              • подай как дружеский совет («А вот, к слову, есть ещё …, арт. …»).  

            ВЫХОД:
            - Один законченный ответ бренда без служебных вставок.
            """)
            resp = all_requests.ask_gpt(prompt, name=self.name)
        else:
            sh = self.gc.open_by_key(GOOGLE_TABLE_KEY_DATA_OF_PATTERNS).worksheet("1 Вариант")
            data = json.dumps(sh.get_all_values(), ensure_ascii=False)
            prompt = (f"Ты автоответчик продавца товара на маркетплейсе Wildberries. Тебе нужно ответить на отзыв покупателя по следующим шаблонам. "
                      f"Данные будут в виде JSON. Если отсутствует ответ на вопрос, значит верным ответом является последний встретившийся. "
                      f"Шаблоны: {data}. Если считаешь, что вопрос следует отклонить, верни строку REJECTED. При необходимости - импровизируй. "
                      f"Если считаешь, что ты не попал в суть вопроса с вероятностью 1/2, то в конце ответа поставь 2 символа *. Если не уверен, что стоит отклонить - не отклоняй. "
                      f"Вот вопрос: {obj.text}")
            resp = all_requests.ask_gpt(prompt, name=self.name)

        reply = ""
        if resp is not None and resp.ok:
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                reply = choices[0].get("message", {}).get("content", "") or ""

        if not reply:
            print(f"[WARN][{self.name}] GPT empty reply")
            if resp is not None:
                all_requests.debug_print_json(resp, name=self.name)

        print(f"[GPT][{self.name}] given text: {getattr(obj, 'text', '')}")
        print(f"[GPT][{self.name}] reply: {reply}")
        return reply

    def _send_reply(self, obj, reply: str):
        if hasattr(obj, "mark"):
            resp = all_requests.send_reply_feedback(self.wb_token, obj.id, reply, name=self.name)
        else:
            state = "none" if reply == "REJECTED" else "wbRu"
            resp = all_requests.send_reply_question(self.wb_token, obj.id, reply, state, name=self.name)
        if resp and resp.ok:
            print(f"[INFO][{self.name}] Sent reply for id={obj.id}")
            return True
        print(f"[WARN][{self.name}] Failed to send reply for id={obj.id}, status={getattr(resp, 'status_code', 'NA')}")
        return False

    def _append_rows_bulk_top(self, name_sheet: str, rows: list[list]):
        if not rows:
            return
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                ws = self.sh.worksheet(name_sheet)
                # вставляем под заголовок (строка 2); rows[::-1] — чтобы «верхом» шла последняя добавленная
                ws.insert_rows(rows[::-1], row=2, value_input_option=ValueInputOption.raw)
                print(f"[INFO][{self.name}] Prepended {len(rows)} rows to sheet '{name_sheet}'")
                break
            except Exception as ex:
                print(f"[WARN][{self.name}] Failed to prepend rows to sheet '{name_sheet}': {ex}")
                time.sleep(ERROR_SLEEP_TIME)

    def update_feedbacks(self):
        rows_to_write = []
        feedbacks = self._get_feedbacks()
        i = 0
        for fb in feedbacks.itertuples():
            reply = self._compose_reply(fb)
            if not reply:
                continue

            date_ans = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            check = self._send_reply(fb, reply)
            if check:
                rows_to_write.append([fb.supplier_article, fb.nm_id, fb.date_fb, fb.mark, fb.text, reply, date_ans])

            i += 1
            if i == 1 and rows_to_write:
                i = 0
                self._append_rows_bulk_top("Отзывы", rows_to_write)
                rows_to_write = []

    def update_questions(self):
        rows_to_write = []
        questions = self._get_questions()
        for q in questions.itertuples():
            reply = self._compose_reply(q)
            if not reply:
                continue
            check = self._send_reply(q, reply)
            if check:
                rows_to_write.append([q.text, q.date_q, reply])
        if rows_to_write:
            ws = self.sh.worksheet("Вопросы")
            ws.insert_rows(rows_to_write[::-1], row=2, value_input_option=ValueInputOption.raw)

    def start_autoresponder(self):
        print(f"[INFO] Start autoresponder for {self.name}")
        self.characteristics = self._get_characteristics()
        self.update_feedbacks()
        # self.update_questions()
