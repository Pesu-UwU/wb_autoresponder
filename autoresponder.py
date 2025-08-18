import gspread
import pandas as pd

import all_requests

class autoresponder:

    def __init__(self, key_table, name, wb_token):
        self.key_table = key_table
        self.name = name
        self.wb_token = wb_token
        gc = gspread.service_account(filename="credentials.json")
        self.sh = gc.open_by_key(key_table)

    def feedback(self):
        result = pd.DataFrame(columns=["id", "text", "date", "mark"])

        take = 5000
        res = all_requests.get_feedback(self.wb_token, "true", take, 0).json()
        cnt_false = res["data"]["countUnanswered"]
        print(cnt_false)

        n = int((cnt_false + take - 1) / take)
        for coef in range(n):
            res = all_requests.get_feedback(self.wb_token, "false", take, coef * take).json()
            for fb in res["data"]["feedbacks"]:
                if fb.get("text"):  # пропускаем пустые
                    result.loc[len(result)] = [fb["id"], fb["text"], fb["createdDate"], fb["productValuation"]]
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

    def question(self):
        result = pd.DataFrame(columns=["id", "text", "date"])

        take = 10000
        res = all_requests.get_quations(self.wb_token, "true", take, 0).json()
        cnt_false = res["data"]["countUnanswered"]
        print(cnt_false)

        n = int((cnt_false + take - 1) / take)
        for coef in range(n):
            res = all_requests.get_feedback(self.wb_token, "false", take, coef * take).json()
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
        raise NotImplementedError("Метод compose_reply еще не реализован")

    def send_reply(self, obj, reply):
        if "mark" in obj:
            all_requests.send_reply_feedback(self.wb_token, obj.id, reply)
            worksheet = self.sh.worksheet("Отзывы")
            worksheet.append_row([obj.text, obj.date, reply])
        else:
            all_requests.send_reply_feedback(self.wb_token, obj.id, reply)
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
        self.update_questions()


