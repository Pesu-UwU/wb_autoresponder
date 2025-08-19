import time
import requests
from dotenv import load_dotenv
import os
from typing import Dict, Any

load_dotenv()

ERROR_SLEEP_TIME = 60
MAX_RETRIES = 3
TIMEOUT = 60

def _request(method: str, url: str, headers: Dict[str, str], params: Dict[str, Any]) -> requests.Response:
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.request(method, url, headers=headers, params=params, timeout=TIMEOUT)
        if (method == "POST" and resp.status_code == 204) or (method in ("GET", "PATCH") and resp.ok):
            print(f"[INFO] HTTP {method} {url} OK ({resp.status_code})")
            return resp
        print(f"[WARN] HTTP {method} {url} -> {resp.status_code} "
              f"(attempt {attempt}/{MAX_RETRIES}). Retry in {ERROR_SLEEP_TIME}s")
        time.sleep(ERROR_SLEEP_TIME)
    # последняя попытка: вернём как есть
    return resp


def get_feedback(token, isAnswered, take, skip):
    return _request(
        "GET",
        "https://feedbacks-api.wildberries.ru/api/v1/feedbacks",
        {"Authorization": token, "Content-Type": "application/json"},
        {"take": take, "isAnswered": isAnswered, "skip": skip, "order": "dateAsc"},
    )

def send_reply_feedback(token, id, reply):
    return _request(
        "POST",
        "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/answer",
        {"Authorization": token, "Content-Type": "application/json"},
        {"id": id, "text": reply},
    )

def get_quastions(token, isAnswered, take, skip):  # можно переименовать на get_questions (API сохраните)
    return _request(
        "GET",
        "https://feedbacks-api.wildberries.ru/api/v1/questions",
        {"Authorization": token, "Content-Type": "application/json"},
        {"take": take, "isAnswered": isAnswered, "skip": skip, "order": "dateAsc"},
    )

def send_reply_question(token, id, reply, state):
    return _request(
        "PATCH",
        "https://feedbacks-api.wildberries.ru/api/v1/questions",
        {"Authorization": token, "Content-Type": "application/json"},
        {"id": id, "answer": {"text": reply}, "state": state},
    )

# def get_feedback(token, isAnswered, take, skip):
#     url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
#     headers = {
#         "Authorization": token,
#         "Content-Type": "application/json"
#     }
#     params = {
#         "take": take,
#         "isAnswered": isAnswered,
#         "skip": skip,
#         "order": "dateAsc"
#     }
#
#     for i in range(3):
#         result = requests.get(url=url, headers=headers, params=params, timeout=60)
#         time.sleep(1)
#         if result.status_code != 200:
#             print(f"Requests get_feedback: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
#             time.sleep(ERROR_SLEEP_TIME)
#         else:
#             break
#     print(f"Requests get_feedback: {result.status_code} STOP")
#     return result
#
# def send_reply_feedback(token, id, reply):
#     url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/answer"
#     headers = {
#         "Authorization": token,
#         "Content-Type": "application/json"
#     }
#     params = {
#         "id": id,
#         "text": reply
#     }
#
#     for i in range(3):
#         result = requests.post(url=url, headers=headers, params=params, timeout=60)
#         time.sleep(1)
#         if result.status_code != 204:
#             print(f"Requests send_reply_feedback: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
#             time.sleep(ERROR_SLEEP_TIME)
#         else:
#             break
#     print(f"Requests send_reply_feedback: {result.status_code} STOP")
#     return result
#
# def get_quations(token, isAnswered, take, skip):
#     url = "https://feedbacks-api.wildberries.ru/api/v1/questions"
#     headers = {
#         "Authorization": token,
#         "Content-Type": "application/json"
#     }
#     params = {
#         "take": take,
#         "isAnswered": isAnswered,
#         "skip": skip,
#         "order": "dateAsc"
#     }
#
#     for i in range(3):
#         result = requests.get(url=url, headers=headers, params=params, timeout=60)
#         time.sleep(1)
#         if result.status_code != 200:
#             print(f"Requests get_quations: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
#             time.sleep(ERROR_SLEEP_TIME)
#         else:
#             break
#     print(f"Requests get_quations: {result.status_code} STOP")
#     return result
#
# def send_reply_question(token, id, reply, state):
#     url = "https://feedbacks-api.wildberries.ru/api/v1/questions"
#     headers = {
#         "Authorization": token,
#         "Content-Type": "application/json"
#     }
#     params = {
#         "id": id,
#         "answer": {
#             "text": reply
#         },
#         "state": state
#     }
#
#     for i in range(3):
#         result = requests.patch(url=url, headers=headers, params=params, timeout=60)
#         time.sleep(1)
#         if result.status_code != 200:
#             print(f"Requests send_reply_question: {result.status_code} REPEAT AFTER {ERROR_SLEEP_TIME} SECOND")
#             time.sleep(ERROR_SLEEP_TIME)
#         else:
#             break
#     print(f"Requests send_reply_question: {result.status_code} STOP")
#     return result

def get_ans_gpt():
    gpt_token = os.getenv("GPT_TOKEN")