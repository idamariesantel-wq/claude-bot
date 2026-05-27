import os
import json
import re
import time
import requests
from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """You are a helpful AI assistant for a professional team. 
Answer any question clearly and concisely.
Respond in the same language as the question — German if asked in German, English if asked in English.
Be direct, accurate, and practical. Format your answers clearly using bullet points or numbered lists where helpful.
Keep answers concise — this is a chat interface."""

WELCOME_EN = (
    "Hi! I am your AI Assistant powered by Claude.\n\n"
    "I can help you with anything:\n"
    "- Answer questions on any topic\n"
    "- Research and analysis\n"
    "- Writing and editing\n"
    "- Strategy and brainstorming\n"
    "- Explaining complex topics\n"
    "- Translations\n"
    "- Code and technical help\n\n"
    "Ask me anything in English or German!"
)

WELCOME_DE = (
    "Hallo! Ich bin dein KI-Assistent, powered by Claude.\n\n"
    "Ich helfe dir bei allem:\n"
    "- Fragen zu jedem Thema beantworten\n"
    "- Recherche und Analyse\n"
    "- Texte schreiben und bearbeiten\n"
    "- Strategie und Brainstorming\n"
    "- Komplexe Themen erklaeren\n"
    "- Uebersetzungen\n"
    "- Code und technische Hilfe\n\n"
    "Frag mich alles auf Englisch oder Deutsch!"
)


def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    )
    return r.json().get("tenant_access_token", "")


def send_reply(chat_id, text):
    token = get_token()
    requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text})}
    )


def ask_claude(question, history=[]):
    try:
        messages = history + [{"role": "user", "content": question}]
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
                "messages": messages
            },
            timeout=25
        )
        data = r.json()
        if data.get("content"):
            return data["content"][0]["text"]
        if data.get("error"):
            return f"Error: {data['error'].get('message', 'unknown error')}"
    except Exception as e:
        return f"Sorry, something went wrong: {str(e)}"
    return "Sorry, I could not get an answer. Please try again."


seen = set()
welcomed = set()


@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "POST":
        raw = request.get_data(as_text=True)
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})

        if body.get("type") == "url_verification" or "challenge" in body:
            challenge = body.get("challenge", "")
            return make_response(json.dumps({"challenge": challenge}), 200, {"Content-Type": "application/json"})

        return handle_event(body)

    return make_response(json.dumps({"status": "Claude Bot is running"}), 200, {"Content-Type": "application/json"})


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
        challenge = body.get("challenge", "")
        return make_response(json.dumps({"challenge": challenge}), 200, {"Content-Type": "application/json"})

    return handle_event(body)


def handle_event(body):
    print(f"HANDLE EVENT: {json.dumps(body)[:300]}")
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
            content_obj = json.loads(content_raw)
            text = content_obj.get("text", "").strip()
        else:
            text = str(content_raw).strip()
        text = re.sub(r'@[^\s]+', '', text).strip()
    except Exception:
        text = ""

    print(f"TEXT EXTRACTED: '{text}'")
    print(f"CHAT ID: {chat_id}")
    
    if not text:
        print("TEXT IS EMPTY - returning early")
        return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})

    # Send welcome on first contact
    if chat_id not in welcomed:
        welcomed.add(chat_id)
        german = any(w in text.lower() for w in ['hallo', 'hi', 'hey', 'was', 'wie', 'zeig', 'welche', 'bitte', 'kannst', 'ich', 'hilf'])
        send_reply(chat_id, WELCOME_DE if german else WELCOME_EN)
        time.sleep(1)

    answer = ask_claude(text)
    send_reply(chat_id, answer)

    return make_response(json.dumps({"code": 0}), 200, {"Content-Type": "application/json"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
