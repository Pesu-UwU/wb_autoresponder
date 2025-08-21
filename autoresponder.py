import gspread
import pandas as pd
from typing import Dict, Any, List

import all_requests
from all_requests import ask_gpt


class autoresponder:

    def __init__(self, key_table, name, wb_token):
        self.key_table = key_table
        self.name = name
        self.wb_token = wb_token
        gc = gspread.service_account(filename="credentials.json")
        self.sh = gc.open_by_key(key_table)

    def feedback(self):
        rows: List[Dict] = []
        #result = pd.DataFrame(columns=["id", "text", "date", "mark"])

        take = 5000
        res = all_requests.get_feedback(self.wb_token, "true", take, 0)
        cnt_false = res["data"]["countUnanswered"]
        print(cnt_false)

        n = int((cnt_false + take - 1) / take)
        for coef in range(n):
            res = all_requests.get_feedback(self.wb_token, "false", take, coef * take)
            for fb in res["data"]["feedbacks"]:
                text = fb.get("text")
                if text:
                    rows.append({
                        "id": fb["id"],
                        "text": text,
                        "date": fb["createdDate"],
                        "mark": fb.get("productValuation"),
                        "user_name": fb.get("userName")
                    })
        return pd.DataFrame(rows, columns=["id", "text", "date", "mark", "user_name"])

    def question(self):
        result = pd.DataFrame(columns=["id", "text", "date"])

        take = 10000
        res = all_requests.get_quations(self.wb_token, "true", take, 0)
        cnt_false = res["data"]["countUnanswered"]
        print(cnt_false)

        n = int((cnt_false + take - 1) / take)
        for coef in range(n):
            res = all_requests.get_feedback(self.wb_token, "false", take, coef * take)
            for q in res["data"]["questions"]:
                if q.get("state") == "suppliersPortalSynch":  # только новые запросы без отклоненных
                    result.loc[len(result)] = [q["id"], q["text"], q["createdDate"]]


                     # ← генератор, удобно для потока
                # fd = i["text"]
                # date = i["createdDate"]
                # mark = i["productValuation"]
                # df = pd.DataFrame(d)
                # if (fd != ""):
                #     print(fd)
                #     print(date)
                #     print(mark)

        return result


    def compose_reply(self, obj): #  будет генериться с помощью api gpt
        reply = ""
        if hasattr(obj, "mark"):
            prompt = (f"Ты продавец товара на маркетплейсе Wildberries. Тебе нужно ответить на отзыв покупателя по следующим шаблонам. Ответы к положительным комментариям (оценка: больше или равна 4):"
                      f"[Добрый день! Спасибо, что нашли время для оценки нашего продукт. Ваши отзывы помогают улучшить качество заказов.\nС уважением, представители бренда!],"
                      f"[Здравствуйте, Надежда! Мы ценим и уважаем каждого клиента. Благодарим за положительный отзыв.\nС уважением, представители бренда!]."
                      f"Ответы к негативному отзыву: "
                      f"[Добрый день. Спешим к вам с извинениями!! Очень жаль, что покупка не смогла вас порадовать.\nС уважением, представители бренда!],"
                      f"[Здраствуйте, Марина! Благодарим Вас за обратную связь. Нам искренне жаль, что Вы разочарованы покупкой.\nС уважением, представители бренда!]."
                      f"Текст отзыва: {obj.text}, оценка отзыва: {obj.mark}, имя клиента: {obj.user_name}. Если у пользователя есть нормальное имя, то обратись к нему по имени. По необходимости можешь отойти от шаблона.")
            data = ask_gpt(prompt)
            reply = data["choices"][0]["message"]["content"]
            print(reply)
        return reply


    def send_reply(self, obj, reply: str):
        if hasattr(obj, "mark"):
            all_requests.send_reply_feedback(self.wb_token, obj.id, reply)
            worksheet = self.sh.worksheet("Отзывы")
            worksheet.append_row([obj.text, obj.date, obj.mark, reply])
        else:
            state = "none" if reply == "Отклонен" else "wbRu"
            all_requests.send_reply_question(self.wb_token, obj.id, reply, state)
            worksheet = self.sh.worksheet("Вопросы")
            worksheet.append_row([obj.text, obj.date, reply])


    def update_feedbacks(self):
        feedbacks = self.feedback()
        for fb in feedbacks.itertuples():
            reply = self.compose_reply(fb)
            self.send_reply(fb, reply)

    def update_questions(self):
        questions = self.question()
        for q in questions.itertuples():
            reply = self.compose_reply(q)
            self.send_reply(q, reply)



    def start_autoresponder(self):
        self.update_feedbacks()
        #self.update_questions()


