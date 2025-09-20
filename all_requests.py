import os
import time
import json
import requests

ERROR_SLEEP_TIME = 60
MAX_RETRIES = 3


def _request(method: str, url: str, headers: dict, timeout: float,
             params: dict | None = None, json: dict | None = None,
             name: str = "UNKNOWN"):
    """Единая обёртка с ретраями и логами по клиенту."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json,
                timeout=60,
            )
            if resp.ok:
                print(f"[INFO][{name}] HTTP {method} {url} OK ({resp.status_code})")
            else:
                print(f"[WARN][{name}] HTTP {method} {url} -> {resp.status_code}")
            return resp
        except requests.exceptions.Timeout:
            print(f"[WARN][{name}] {method} {url} Timeout (attempt {attempt}/{MAX_RETRIES}). Retry in {ERROR_SLEEP_TIME}s")
            time.sleep(ERROR_SLEEP_TIME)
        except requests.exceptions.RequestException as ex:
            print(f"[WARN][{name}] {method} {url} error: {ex} (attempt {attempt}/{MAX_RETRIES}). Retry in {ERROR_SLEEP_TIME}s")
            time.sleep(ERROR_SLEEP_TIME)
        except Exception as ex:
            print(f"[WARN][{name}] {method} {url} unexpected error: {ex} (attempt {attempt}/{MAX_RETRIES}). Retry in {ERROR_SLEEP_TIME}s")
            time.sleep(ERROR_SLEEP_TIME)
    return None


def debug_print_json(resp, name: str = "UNKNOWN"):
    try:
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except Exception as ex:
        print(f"[WARN][{name}] debug_print_json failed: {ex}")


# ------------------ WB FEEDBACKS / QUESTIONS ------------------

def get_feedbacks(token: str, unanswered: str, take: int, skip: int, name: str):
    return _request(
        "GET",
        "https://feedbacks-api.wildberries.ru/api/v1/feedbacks",
        {"Authorization": token},
        0.4,
        params={"isAnswered": unanswered, "take": take, "skip": skip},
        name=name,
    )


def send_reply_feedback(token: str, fb_id: int, reply: str, name: str):
    return _request(
        "POST",
        "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/comments",
        {"Authorization": token, "Content-Type": "application/json"},
        0.4,
        json={"id": fb_id, "text": reply},
        name=name,
    )


def get_questions(token: str, unanswered: str, take: int, skip: int, name: str):
    return _request(
        "GET",
        "https://feedbacks-api.wildberries.ru/api/v1/questions",
        {"Authorization": token},
        0.4,
        params={"isAnswered": unanswered, "take": take, "skip": skip},
        name=name,
    )


def send_reply_question(token: str, q_id: int, reply: str, state: str, name: str):
    # важно: тело именно JSON, не params
    return _request(
        "PATCH",
        "https://feedbacks-api.wildberries.ru/api/v1/questions",
        {"Authorization": token, "Content-Type": "application/json"},
        0.4,
        json={"id": q_id, "answer": {"text": reply}, "state": state},
        name=name,
    )


# ------------------ WB CONTENT CARDS ------------------

def get_cards(token: str, limit: int, nm_id: int | None, updated_at: str | None, name: str):
    cursor = {"limit": limit}
    if nm_id is not None:
        cursor["nmID"] = nm_id
    if updated_at is not None:
        cursor["updatedAt"] = updated_at

    body = {
        "settings": {
            "cursor": cursor,
            "sort": {"ascending": False},
            "filter": {
                "textSearch": "",
                "withPhoto": -1,            # все карточки (и с фото, и без)
                "allowedStatuses": [],
                "objectIDs": [],
                "brandNames": [],
                "tagIDs": []
            }
        }
    }
    return _request(
        "POST",
        "https://content-api.wildberries.ru/content/v2/get/cards/list",
        {"Authorization": token, "Content-Type": "application/json"},
        0.4,
        json=body,
        name=name,
    )


# ------------------ OPENAI ------------------

def ask_gpt(prompt: str, name: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(f"[WARN][{name}] OPENAI_API_KEY not set")
        return None
    return _request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        0.4,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        },
        name=name,
    )
