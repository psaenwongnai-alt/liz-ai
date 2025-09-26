# -*- coding: utf-8 -*-
import os, json, time, atexit, requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import openai
from io import BytesIO

# -----------------------------
# Config
# -----------------------------
SESSION_FILE = Path("liz_memory.json")
SLEEP_TIMEOUT = 15 * 60  # 15 นาที idle
LANGUAGES = ["th", "en", "zh", "ko", "ja"]
MODES = [
    "friendly", "serious", "advice", "fun", "music", "translate", "summary",
    "tts"
]

openai.api_key = os.environ.get("OPENAI_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

# -----------------------------
# Flask App
# -----------------------------
app = Flask(__name__, static_folder="public")
CORS(app)

# -----------------------------
# Memory & Trait
# -----------------------------
memory = {
    "last_active": time.time(),
    "history": [],
    "liz_on": True,
    "mode": "friendly",
    "mood": "calm",
    "empathy": 80,
    "curiosity": 60,
    "fun": 50,
    "serious": 70
}


def save_memory():
    SESSION_FILE.write_text(json.dumps(memory, ensure_ascii=False))


def load_memory():
    global memory
    if SESSION_FILE.exists():
        memory = json.loads(SESSION_FILE.read_text())


load_memory()


# -----------------------------
# YouTube Helper
# -----------------------------
def search_youtube(query):
    try:
        params = {
            "part": "snippet",
            "q": query,
            "key": YOUTUBE_API_KEY,
            "type": "video",
            "maxResults": 1
        }
        resp = requests.get(YOUTUBE_SEARCH_URL, params=params).json()
        if "items" in resp and len(resp["items"]) > 0:
            video_id = resp["items"][0]["id"]["videoId"]
            deeplink = f"vnd.youtube://{video_id}"  # มือถือ
            web_link = f"https://youtu.be/{video_id}"  # เว็บ
            return deeplink, web_link
    except Exception as e:
        print("YouTube search error:", e)
    return None, None


# -----------------------------
# AI Chat
# -----------------------------
def chat_with_liz(user_input, lang="auto", mode=None):
    global memory
    now = time.time()

    if now - memory.get("last_active", now) > SLEEP_TIMEOUT:
        memory["liz_on"] = False

    if not memory.get("liz_on", True):
        memory["liz_on"] = True
        memory["last_active"] = now
        save_memory()
        return "Liz กำลังพักอยู่... เรียกใช้งานครั้งนี้ปลุก Liz แล้ว"

    memory["last_active"] = now
    memory["history"].append({"role": "user", "content": user_input})
    save_memory()

    mode = mode or memory.get("mode", "friendly")

    if mode == "music":
        if "youtube.com" in user_input or "youtu.be" in user_input:
            reply = f"🎵 เปิดเพลงจาก YouTube: {user_input}"
        else:
            deeplink, web_link = search_youtube(user_input)
            if deeplink:
                reply = f"🎶 เจอเพลงให้แล้ว:\n- มือถือ: {deeplink}\n- เว็บ: {web_link}"
            else:
                reply = "หาเพลงนี้ไม่เจอใน YouTube 😢"
        memory["history"].append({"role": "liz", "content": reply})
        save_memory()
        return reply

    elif mode == "summary":
        try:
            system_prompt = f"สรุปข้อความนี้ให้สั้นและชัดเจน:\n{user_input}"
            response = openai.ChatCompletion.create(model="gpt-4o-mini",
                                                    messages=[{
                                                        "role":
                                                        "system",
                                                        "content":
                                                        system_prompt
                                                    }],
                                                    max_tokens=150)
            reply = response.choices[0].message.content.strip()
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "เกิดข้อผิดพลาดในการสรุปข้อความ"

    elif mode == "translate":
        try:
            system_prompt = f"แปลข้อความนี้เป็นหลายภาษา: {user_input}"
            response = openai.ChatCompletion.create(model="gpt-4o-mini",
                                                    messages=[{
                                                        "role":
                                                        "system",
                                                        "content":
                                                        system_prompt
                                                    }],
                                                    max_tokens=200)
            reply = response.choices[0].message.content.strip()
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "เกิดข้อผิดพลาดในการแปล"

    system_prompt = f"""
คุณคือลิซ ผู้ช่วย AI สุดยอด (สายกลาง)
- Mood: {memory['mood']}
- Empathy: {memory['empathy']}
- Curiosity: {memory['curiosity']}
- Fun: {memory['fun']}
- Serious: {memory['serious']}
- Conversation history: {memory['history']}
ตอบผู้ใช้ตาม mode {mode} อย่างเหมาะสม
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
        audio_resp = openai.audio.speech.create(model="tts-1",
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
    # ส่ง index.html จาก public/
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:filename>")
def public_files(filename):
    # ส่งไฟล์ static อื่นๆ จาก public/
    return send_from_directory(app.static_folder, filename)


@app.route("/talk", methods=["POST"])
def talk():
    data = request.json
    text = data.get("text", "")
    lang = data.get("lang", "auto")
    mode = data.get("mode")
    reply = chat_with_liz(text, lang, mode)
    return jsonify({"response": reply})


@app.route("/sleep", methods=["POST"])
def sleep_route():
    memory["liz_on"] = False
    save_memory()
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


@app.route("/set_mode", methods=["POST"])
def set_mode():
    data = request.json
    mode = data.get("mode", "friendly")
    if mode in MODES:
        memory["mode"] = mode
        save_memory()
        return jsonify({"status": "mode set", "mode": mode})
    else:
        return jsonify({"error": "invalid mode"}), 400


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
