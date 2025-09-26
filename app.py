# -*- coding: utf-8 -*-
import os, json, time, threading, atexit, requests, smtplib
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import openai
from io import BytesIO
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# -----------------------------
# Config
# -----------------------------
SESSION_FILE = Path("liz_memory.json")
SLEEP_TIMEOUT = 15 * 60
LANGUAGES = ["th", "en", "zh", "ko", "ja"]
MODES = [
    "friendly", "serious", "advice", "fun", "music", "news",
    "translate", "tts", "summary", "reminder", "sleep", "wake"
]

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")  # สำหรับโหมดข่าว

openai.api_key = os.environ.get("OPENAI_API_KEY")

# -----------------------------
# Flask App
# -----------------------------
app = Flask(__name__)
CORS(app)

# -----------------------------
# Spotify Client
# -----------------------------
spotify_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
    client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET")
))

# -----------------------------
# Memory
# -----------------------------
memory = {
    "last_active": datetime.now().isoformat(),
    "history": [],
    "liz_on": True,
    "mood": "neutral",
    "mode": "friendly",
    "reminders": []
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
# Reminder Background Thread
# -----------------------------
def reminder_check():
    while True:
        now = datetime.now()
        for r in memory.get("reminders", []):
            reminder_time = datetime.fromisoformat(r["time"])
            if now >= reminder_time and not r.get("sent"):
                message = f"⏰ Reminder: {r['note']}"
                send_notification(message)
                r["sent"] = True
                save_memory()
        time.sleep(30)  # ตรวจสอบทุก 30 วินาที


def send_notification(message):
    # --- ตัวอย่างส่ง Line Notify ---
    token = os.environ.get("LINE_NOTIFY_TOKEN")
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": message}
        requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data)

    # --- ตัวอย่างส่ง Telegram ---
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message})

    # --- ตัวอย่างส่ง Email ---
    user = os.environ.get("EMAIL_USER")
    passwd = os.environ.get("EMAIL_PASS")
    if user and passwd:
        try:
            smtp = smtplib.SMTP("smtp.gmail.com", 587)
            smtp.starttls()
            smtp.login(user, passwd)
            smtp.sendmail(user, user, message)
            smtp.quit()
        except:
            pass


threading.Thread(target=reminder_check, daemon=True).start()

# -----------------------------
# AI Chat with Modes
# -----------------------------
def chat_with_liz(user_input, lang="auto", mode=None):
    if not memory.get("liz_on", True):
        return "Liz กำลังหลับอยู่..."

    wake_liz()
    memory["last_active"] = datetime.now().isoformat()
    memory["history"].append({"role": "user", "content": user_input})
    save_memory()

    mode = mode or memory.get("mode", "friendly")

    # --- โหมด music ---
    if mode == "music":
        try:
            if "spotify.com/track/" in user_input:
                track_id = user_input.split("track/")[1].split("?")[0]
                track = spotify_client.track(track_id)
                reply = f"🎵 เล่นเพลง: {track['name']} - {track['artists'][0]['name']}\n{track['external_urls']['spotify']}"
            else:
                reply = f"🎵 เล่นเพลงจาก URL: {user_input}"
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "ไม่สามารถเล่นเพลงได้ ตรวจสอบ URL หรือ Spotify credentials"

    # --- โหมด news ---
    elif mode == "news":
        try:
            url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
            res = requests.get(url).json()
            articles = res.get("articles", [])[:3]
            reply = "\n".join([f"- {a['title']}" for a in articles])
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply or "ไม่พบข่าวล่าสุด"
        except:
            return "เกิดข้อผิดพลาดในการดึงข่าว"

    # --- โหมด summary ---
    elif mode == "summary":
        try:
            system_prompt = f"สรุปข้อความนี้ให้สั้นและชัดเจน:\n{user_input}"
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                max_tokens=150
            )
            reply = response.choices[0].message.content.strip()
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "เกิดข้อผิดพลาดในการสรุปข้อความ"

    # --- โหมด translate ---
    elif mode == "translate":
        try:
            system_prompt = f"แปลข้อความนี้เป็นหลายภาษา: {user_input}"
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                max_tokens=200
            )
            reply = response.choices[0].message.content.strip()
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "เกิดข้อผิดพลาดในการแปล"

    # --- โหมดทั่วไป friendly, serious, advice, fun ---
    system_prompt = f"""
คุณคือลิซ ผู้ช่วยส่วนตัว โหมด: {mode}
- เป็นล่าม 5 ภาษา: ไทย, อังกฤษ, จีน, เกาหลี, ญี่ปุ่น
- ตอบกลับผู้ใช้ตามภาษาอัตโนมัติ
- จำบริบท ตัวตน mood ของผู้ใช้
- ตอบชัดเจน สั้น กระชับ
Conversation history: {memory['history']}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=250
        )
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
        audio_resp = openai.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        )
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
    mode = data.get("mode")
    reply = chat_with_liz(text, lang, mode)
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


@app.route("/reminder", methods=["POST"])
def reminder():
    data = request.json
    note = data.get("note", "")
    timestamp = data.get("time", datetime.now().isoformat())
    memory["reminders"].append({"note": note, "time": timestamp})
    save_memory()
    return jsonify({"status": "reminder set"})


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
# -*- coding: utf-8 -*-
import os, json, time, threading, atexit, requests, smtplib
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import openai
from io import BytesIO
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# -----------------------------
# Config
# -----------------------------
SESSION_FILE = Path("liz_memory.json")
SLEEP_TIMEOUT = 15 * 60
LANGUAGES = ["th", "en", "zh", "ko", "ja"]
MODES = [
    "friendly", "serious", "advice", "fun", "music", "news",
    "translate", "tts", "summary", "reminder", "sleep", "wake"
]

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")  # สำหรับโหมดข่าว

openai.api_key = os.environ.get("OPENAI_API_KEY")

# -----------------------------
# Flask App
# -----------------------------
app = Flask(__name__)
CORS(app)

# -----------------------------
# Spotify Client
# -----------------------------
spotify_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
    client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET")
))

# -----------------------------
# Memory
# -----------------------------
memory = {
    "last_active": datetime.now().isoformat(),
    "history": [],
    "liz_on": True,
    "mood": "neutral",
    "mode": "friendly",
    "reminders": []
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
# Reminder Background Thread
# -----------------------------
def reminder_check():
    while True:
        now = datetime.now()
        for r in memory.get("reminders", []):
            reminder_time = datetime.fromisoformat(r["time"])
            if now >= reminder_time and not r.get("sent"):
                message = f"⏰ Reminder: {r['note']}"
                send_notification(message)
                r["sent"] = True
                save_memory()
        time.sleep(30)  # ตรวจสอบทุก 30 วินาที


def send_notification(message):
    # --- ตัวอย่างส่ง Line Notify ---
    token = os.environ.get("LINE_NOTIFY_TOKEN")
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": message}
        requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data)

    # --- ตัวอย่างส่ง Telegram ---
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message})

    # --- ตัวอย่างส่ง Email ---
    user = os.environ.get("EMAIL_USER")
    passwd = os.environ.get("EMAIL_PASS")
    if user and passwd:
        try:
            smtp = smtplib.SMTP("smtp.gmail.com", 587)
            smtp.starttls()
            smtp.login(user, passwd)
            smtp.sendmail(user, user, message)
            smtp.quit()
        except:
            pass


threading.Thread(target=reminder_check, daemon=True).start()

# -----------------------------
# AI Chat with Modes
# -----------------------------
def chat_with_liz(user_input, lang="auto", mode=None):
    if not memory.get("liz_on", True):
        return "Liz กำลังหลับอยู่..."

    wake_liz()
    memory["last_active"] = datetime.now().isoformat()
    memory["history"].append({"role": "user", "content": user_input})
    save_memory()

    mode = mode or memory.get("mode", "friendly")

    # --- โหมด music ---
    if mode == "music":
        try:
            if "spotify.com/track/" in user_input:
                track_id = user_input.split("track/")[1].split("?")[0]
                track = spotify_client.track(track_id)
                reply = f"🎵 เล่นเพลง: {track['name']} - {track['artists'][0]['name']}\n{track['external_urls']['spotify']}"
            else:
                reply = f"🎵 เล่นเพลงจาก URL: {user_input}"
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "ไม่สามารถเล่นเพลงได้ ตรวจสอบ URL หรือ Spotify credentials"

    # --- โหมด news ---
    elif mode == "news":
        try:
            url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
            res = requests.get(url).json()
            articles = res.get("articles", [])[:3]
            reply = "\n".join([f"- {a['title']}" for a in articles])
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply or "ไม่พบข่าวล่าสุด"
        except:
            return "เกิดข้อผิดพลาดในการดึงข่าว"

    # --- โหมด summary ---
    elif mode == "summary":
        try:
            system_prompt = f"สรุปข้อความนี้ให้สั้นและชัดเจน:\n{user_input}"
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                max_tokens=150
            )
            reply = response.choices[0].message.content.strip()
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "เกิดข้อผิดพลาดในการสรุปข้อความ"

    # --- โหมด translate ---
    elif mode == "translate":
        try:
            system_prompt = f"แปลข้อความนี้เป็นหลายภาษา: {user_input}"
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                max_tokens=200
            )
            reply = response.choices[0].message.content.strip()
            memory["history"].append({"role": "liz", "content": reply})
            save_memory()
            return reply
        except:
            return "เกิดข้อผิดพลาดในการแปล"

    # --- โหมดทั่วไป friendly, serious, advice, fun ---
    system_prompt = f"""
คุณคือลิซ ผู้ช่วยส่วนตัว โหมด: {mode}
- เป็นล่าม 5 ภาษา: ไทย, อังกฤษ, จีน, เกาหลี, ญี่ปุ่น
- ตอบกลับผู้ใช้ตามภาษาอัตโนมัติ
- จำบริบท ตัวตน mood ของผู้ใช้
- ตอบชัดเจน สั้น กระชับ
Conversation history: {memory['history']}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=250
        )
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
        audio_resp = openai.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        )
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
    mode = data.get("mode")
    reply = chat_with_liz(text, lang, mode)
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


@app.route("/reminder", methods=["POST"])
def reminder():
    data = request.json
    note = data.get("note", "")
    timestamp = data.get("time", datetime.now().isoformat())
    memory["reminders"].append({"note": note, "time": timestamp})
    save_memory()
    return jsonify({"status": "reminder set"})


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
