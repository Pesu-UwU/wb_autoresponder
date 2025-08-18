import time
import requests
from dotenv import load_dotenv
import os

load_dotenv()

ERROR_SLEEP_TIME = 60

def get_feedback(token, isAnswered, take, skip):
    url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    params = {
        "take": take,
        "isAnswered": isAnswered,
        "skip": skip,
        "order": "dateAsc"
    }

    for i in range(3):
        result = requests.get(url=url, headers=headers, params=params, timeout=60)
        time.sleep(1)
        if result.status_code != 200:
            print(f"Requests get_feedback: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
            time.sleep(ERROR_SLEEP_TIME)
        else:
            break
    print(f"Requests get_feedback: {result.status_code} STOP")
    return result

def send_reply_feedback(token, id, reply):
    url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/answer"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    params = {
        "id": id,
        "text": reply
    }

    for i in range(3):
        result = requests.post(url=url, headers=headers, params=params, timeout=60)
        time.sleep(1)
        if result.status_code != 204:
            print(f"Requests send_reply_feedback: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
            time.sleep(ERROR_SLEEP_TIME)
        else:
            break
    print(f"Requests send_reply_feedback: {result.status_code} STOP")
    return result

def get_quations(token, isAnswered, take, skip):
    url = "https://feedbacks-api.wildberries.ru/api/v1/questions"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    params = {
        "take": take,
        "isAnswered": isAnswered,
        "skip": skip,
        "order": "dateAsc"
    }

    for i in range(3):
        result = requests.get(url=url, headers=headers, params=params, timeout=60)
        time.sleep(1)
        if result.status_code != 200:
            print(f"Requests get_quations: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
            time.sleep(ERROR_SLEEP_TIME)
        else:
            break
    print(f"Requests get_quations: {result.status_code} STOP")
    return result

def send_reply_question(token, id, reply, state):
    url = "https://feedbacks-api.wildberries.ru/api/v1/questions"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    params = {
        "id": id,
        "answer": {
            "text": reply
        },
        "state": state
    }

    for i in range(3):
        result = requests.patch(url=url, headers=headers, params=params, timeout=60)
        time.sleep(1)
        if result.status_code != 200:
            print(f"Requests send_reply_question: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
            time.sleep(ERROR_SLEEP_TIME)
        else:
            break
    print(f"Requests send_reply_question: {result.status_code} STOP")
    return result

def get_ans_gpt():
    gpt_token = os.getenv("GPT_TOKEN")