# -*- coding: utf-8 -*-
import os, json, time, threading, atexit
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import openai
from io import BytesIO

# -----------------------------
# Config
# -----------------------------
SESSION_FILE = Path("liz_memory.json")
SLEEP_TIMEOUT = 15 * 60
LANGUAGES = ["th", "en", "zh", "ko", "ja"]

openai.api_key = os.environ.get("OPENAI_API_KEY")

# -----------------------------
# Flask App
# -----------------------------
app = Flask(__name__)
CORS(app)

# -----------------------------
# Memory
# -----------------------------
memory = {
    "last_active": datetime.now().isoformat(),
    "history": [],
    "liz_on": True,
    "mood": "neutral"
}


def save_memory():
    SESSION_FILE.write_text(json.dumps(memory, ensure_ascii=False))


def load_memory():
    global memory
    if SESSION_FILE.exists():
        memory = json.loads(SESSION_FILE.read_text())


load_memory()

# -----------------------------
# Sleep/Wake
# -----------------------------
liz_awake = True


def sleep_check():
    global liz_awake
    while True:
        if liz_awake and memory.get("liz_on", True):
            last = datetime.fromisoformat(memory["last_active"])
            if (datetime.now() - last) > timedelta(seconds=SLEEP_TIMEOUT):
                liz_awake = False
                memory["liz_on"] = False
                save_memory()
                print("[SYSTEM] Liz เข้านอนอัตโนมัติ")
        time.sleep(5)


threading.Thread(target=sleep_check, daemon=True).start()


def wake_liz():
    global liz_awake
    liz_awake = True
    memory["last_active"] = datetime.now().isoformat()
    memory["liz_on"] = True
    save_memory()


def sleep_liz():
    global liz_awake
    liz_awake = False
    memory["liz_on"] = False
    save_memory()


# -----------------------------
# AI Chat
# -----------------------------
def chat_with_liz(user_input, lang="auto"):
    if not memory.get("liz_on", True):
        return "Liz กำลังหลับอยู่..."

    wake_liz()
    memory["last_active"] = datetime.now().isoformat()
    memory["history"].append({"role": "user", "content": user_input})
    save_memory()

    system_prompt = f"""
คุณคือลิซ ผู้ช่วยส่วนตัว friendly
- เป็นล่าม 5 ภาษา: ไทย, อังกฤษ, จีน, เกาหลี, ญี่ปุ่น
- ตอบกลับผู้ใช้ตามภาษาอัตโนมัติ
- จำบริบท ตัวตน mood ของผู้ใช้
- ตอบชัดเจน สั้น กระชับ
Conversation history: {memory['history']}
"""
    try:
        response = openai.ChatCompletion.create(model="gpt-4o-mini",
                                                messages=[{
                                                    "role":
                                                    "system",
                                                    "content":
                                                    system_prompt
                                                }],
                                                max_tokens=250)
        reply = response.choices[0].message.content.strip()
        memory["history"].append({"role": "liz", "content": reply})
        save_memory()
        return reply
    except Exception as e:
        return f"AI error: {e}"


# -----------------------------
# TTS
# -----------------------------
def generate_tts(text):
    try:
        audio_resp = openai.audio.speech.create(model="gpt-4o-mini-tts",
                                                voice="alloy",
                                                input=text)
        audio_bytes = BytesIO(audio_resp.read())
        return audio_bytes
    except Exception as e:
        print("TTS error:", e)
        return None


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/talk", methods=["POST"])
def talk():
    data = request.json
    text = data.get("text", "")
    lang = data.get("lang", "auto")
    reply = chat_with_liz(text, lang)
    return jsonify({"response": reply})


@app.route("/wake", methods=["POST"])
def wake():
    wake_liz()
    return jsonify({"status": "awake"})


@app.route("/sleep", methods=["POST"])
def sleep_route():
    sleep_liz()
    return jsonify({"status": "sleep"})


@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")
    audio = generate_tts(text)
    if audio:
        audio.seek(0)
        return send_file(audio, mimetype="audio/mpeg")
    else:
        return jsonify({"error": "TTS failed"}), 500


# -----------------------------
# Cleanup
# -----------------------------
def cleanup():
    save_memory()


atexit.register(cleanup)

# -----------------------------
# Run Flask
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
