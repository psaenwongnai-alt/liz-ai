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
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")  # ต้องใส่ API Key
CITY = "Bangkok,TH"  # เปลี่ยนเมืองได้ตามต้องการ
SLEEP_TIMEOUT = 15 * 60

MODES = [
    "friendly", "serious", "advice", "fun", "music", "translate", "summary",
    "tts"
]

openai.api_key = os.environ.get("OPENAI_API_KEY")

# -----------------------------
# Flask App
# -----------------------------
app = Flask(__name__, static_folder="public")
CORS(app)

# -----------------------------
# Memory
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
# Weather helper
# -----------------------------
def get_weather():
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&units=metric&appid={OPENWEATHER_API_KEY}"
        r = requests.get(url).json()
        temp = r['main']['temp']
        desc = r['weather'][0]['description']
        return f"{temp}°C, {desc}"
    except:
        return "Weather unavailable"


# -----------------------------
# AI Chat
# -----------------------------
def chat_with_liz(user_input, mode=None):
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

    # ถ้าเจอคำสั่งหยุดงาน
    if user_input.lower() in ["เลิกงาน", "หยุดทำงาน"]:
        memory["liz_on"] = False
        save_memory()
        return "Liz หยุดทำงานแล้ว"

    # GPT response
    system_prompt = f"""
คุณคือลิซ ผู้ช่วย AI
- Mood: {memory['mood']}
- Empathy: {memory['empathy']}
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
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:filename>")
def public_files(filename):
    return send_from_directory(app.static_folder, filename)


@app.route("/talk", methods=["POST"])
def talk():
    data = request.json
    text = data.get("text", "")
    mode = data.get("mode")
    reply = chat_with_liz(text, mode)
    return jsonify({"response": reply})


@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")
    audio = generate_tts(text)
    if audio:
        audio.seek(0)
        return send_file(audio, mimetype="audio/mpeg")
    return jsonify({"error": "TTS failed"}), 500


@app.route("/set_mode", methods=["POST"])
def set_mode():
    data = request.json
    mode = data.get("mode", "friendly")
    if mode in MODES:
        memory["mode"] = mode
        save_memory()
        return jsonify({"status": "mode set", "mode": mode})
    return jsonify({"error": "invalid mode"}), 400


@app.route("/weather")
def weather_route():
    return jsonify({
        "weather": get_weather(),
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# -----------------------------
# Cleanup
# -----------------------------
atexit.register(save_memory)

# -----------------------------
# Run Flask
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
