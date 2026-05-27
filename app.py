import os
import json
import re
import requests
from flask import Flask, request, make_response

app = Flask(__name__)

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """You are a helpful AI assistant for a professional team.
Answer any question clearly and concisely.
Respond in the same language as the question — German if asked in German, English if asked in English.
Be direct, accurate, and practical. Format answers clearly using bullet points where helpful.
Keep answers concise — this is a chat interface."""


def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10
    )
    return r.json().get("tenant_access_token", "")


def send_reply(chat_id, text):
    try:
        token = get_token()
        requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text})},
            timeout=10
        )
    except Exception as e:
        print(f"SEND ERROR: {e}")


def ask_claude(question):
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": question}]
            },
            timeout=25
        )
        data = r.json()
        if data.get("content"):
            return data["content"][0]["text"]
        if data.get("error"):
            return "Error: " + data["error"].get("message", "unknown")
    except Exception as e:
        return f"Error: {str(e)}"
    return "Sorry, could not get an answer. Please try again."


import threading
seen = set()


def handle_event(body):
    event = body.get("event", {})
    msg = event.get("message", {})
    chat_id = msg.get("chat_id", "") or event.get("open_chat_id", "")
    msg_id = msg.get("message_id", "") or event.get("message_id", "")
    content_raw = msg.get("content", "") or event.get("text", "")

    if not chat_id:
        return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})

    if msg_id in seen:
        return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})
    if msg_id:
        seen.add(msg_id)

    try:
        if isinstance(content_raw, str) and content_raw.strip().startswith("{"):
            text = json.loads(content_raw).get("text", "").strip()
        else:
            text = str(content_raw).strip()
        text = re.sub(r'@[^\s]+', '', text).strip()
    except Exception:
        text = ""

    if not text:
        return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})

    def reply():
        answer = ask_claude(text)
        send_reply(chat_id, answer)

    t = threading.Thread(target=reply)
    t.daemon = True
    t.start()

    return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})


@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "POST":
        raw = request.get_data(as_text=True)
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})
        if body.get("type") == "url_verification" or "challenge" in body:
            return make_response(json.dumps({"challenge": body.get("challenge", "")}), 200, {"Content-Type": "application/json"})
        return handle_event(body)
    return make_response(json.dumps({"status": "Claude Bot running"}), 200, {"Content-Type": "application/json"})


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})
    raw = request.get_data(as_text=True)
    try:
        body = json.loads(raw) if raw else {}
    except Exception:
        return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})
    if body.get("type") == "url_verification" or "challenge" in body:
        return make_response(json.dumps({"challenge": body.get("challenge", "")}), 200, {"Content-Type": "application/json"})
    return handle_event(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
