# all_requests.py
import os
import time
import json
import random
import requests
from typing import Optional

# базовые настройки ретраев
MAX_RETRIES = 3
ERROR_SLEEP_TIME = 60       # fallback, если ничего не известно
BACKOFF_BASE = 30           # базовая задержка для экспоненциального backoff (сек)
BACKOFF_FACTOR = 2.0        # множитель
JITTER_MAX = 5.0            # +/- секунд к задержке, чтобы разрядить шипы

RETRIABLE_STATUS = {429, 500, 502, 503, 504}


def _pretty_err_text(resp: Optional[requests.Response]) -> str:
    """Аккуратно вытащить краткое описание ошибки из ответа (если это JSON)."""
    if resp is None:
        return ""
    try:
        data = resp.json()
        # OpenAI-стиль: {"error": {"message": "...", "type": "...", "code": "..."}}
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            msg = err.get("message") or ""
            typ = err.get("type") or ""
            code = err.get("code") or ""
            parts = []
            if typ: parts.append(f"type={typ}")
            if code: parts.append(f"code={code}")
            if msg: parts.append(f"msg={msg}")
            return "; ".join(parts)
        # Иной JSON — покажем первые 200 символов
        return json.dumps(data, ensure_ascii=False)[:200]
    except Exception:
        # не JSON — вернём первые 200 символов текста
        try:
            return (resp.text or "")[:200]
        except Exception:
            return ""


def _retry_after_seconds(resp: Optional[requests.Response]) -> Optional[float]:
    """Попробовать уважить Retry-After из заголовков (секунды)."""
    if resp is None:
        return None
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)
    except Exception:
        return None


def _compute_delay(resp: Optional[requests.Response], attempt: int) -> float:
    """Задержка до следующей попытки: Retry-After или экспоненциальный backoff + джиттер."""
    ra = _retry_after_seconds(resp)
    if ra is not None:
        return max(ra, 1.0)
    delay = BACKOFF_BASE * (BACKOFF_FACTOR ** (attempt - 1))
    delay += random.uniform(-JITTER_MAX, JITTER_MAX)
    return max(1.0, delay)


def _request(method: str, url: str, headers: dict, timeout: float,
             params: dict | None = None, json: dict | None = None,
             name: str = "UNKNOWN") -> Optional[requests.Response]:
    """
    Универсальная обёртка с ретраями, расширенными логами и уважением Retry-After.
    """
    last_resp = None
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
            last_resp = resp

            if resp.ok:
                print(f"[INFO][{name}] HTTP {method} {url} OK ({resp.status_code})")
                return resp

            # не OK → логируем подробно
            err_text = _pretty_err_text(resp)
            if resp.status_code in RETRIABLE_STATUS and attempt < MAX_RETRIES:
                delay = _compute_delay(resp, attempt)
                print(f"[WARN][{name}] HTTP {method} {url} -> {resp.status_code} "
                      f"(attempt {attempt}/{MAX_RETRIES}). Retry in {int(delay)}s. {err_text}")
                time.sleep(delay)
                continue

            # неуспешный финал или неретраибл — лог и выход
            print(f"[WARN][{name}] HTTP {method} {url} -> {resp.status_code}. {err_text}")
            return resp

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                delay = _compute_delay(None, attempt)
                print(f"[WARN][{name}] {method} {url} Timeout "
                      f"(attempt {attempt}/{MAX_RETRIES}). Retry in {int(delay)}s")
                time.sleep(delay)
                continue
            print(f"[WARN][{name}] {method} {url} Timeout (final)")
            return None

        except requests.exceptions.RequestException as ex:
            if attempt < MAX_RETRIES:
                delay = _compute_delay(None, attempt)
                print(f"[WARN][{name}] {method} {url} error: {ex} "
                      f"(attempt {attempt}/{MAX_RETRIES}). Retry in {int(delay)}s")
                time.sleep(delay)
                continue
            print(f"[WARN][{name}] {method} {url} error: {ex} (final)")
            return last_resp

        except Exception as ex:
            if attempt < MAX_RETRIES:
                delay = _compute_delay(None, attempt)
                print(f"[WARN][{name}] {method} {url} unexpected error: {ex} "
                      f"(attempt {attempt}/{MAX_RETRIES}). Retry in {int(delay)}s")
                time.sleep(delay)
                continue
            print(f"[WARN][{name}] {method} {url} unexpected error: {ex} (final)")
            return last_resp

    return last_resp


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
