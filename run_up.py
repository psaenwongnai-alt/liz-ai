# -*- coding: utf-8 -*-
import os, subprocess, shutil, time, atexit, hashlib, sys, threading
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --------------------------
# Config
# --------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "psaenwongnai-alt/liz-ai"
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
SERVICE_ACCOUNT_PATH = Path("secrets/firebase-service-account.json")
FIREBASE_PROJECT = "liz-ai-project"

LOG_FILE = "deploy_history.log"
CRITICAL_FILES = [
    "app.py", "requirements.txt", "public/index.html", "public/style.css",
    "public/hud5.js", "public/icon.png", "public/ting.mp3"
]
CRITICAL_SECRETS = [".env"]
APP_PROCESS = None
PORT = int(os.environ.get("PORT", "3000"))
LOCAL_URL = f"http://localhost:{PORT}"
VERCEL_URL = None
FIREBASE_URL = f"https://{FIREBASE_PROJECT}.web.app"

STATUS = "IDLE"  # HUD status

# --------------------------
# Logging
# --------------------------
def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

# --------------------------
# HUD animation
# --------------------------
HUD_FRAMES = ["[   ]", "[=  ]", "[== ]", "[===]", "[ ==]", "[  =]"]

def hud_animation():
    idx = 0
    while True:
        frame = HUD_FRAMES[idx % len(HUD_FRAMES)]
        urls = f"Local: {LOCAL_URL} | Firebase: {FIREBASE_URL} | Vercel: {VERCEL_URL or '...' }"
        sys.stdout.write(f"\r💻 Liz AI Status: {STATUS} {frame} | {urls}        ")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.2)

# --------------------------
# Helper functions
# --------------------------
def run(cmd, silent=False):
    try:
        if silent:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        log(f"❌ Command failed: {cmd} -> {e}")

def file_hash(path):
    path = Path(path)
    if not path.exists(): return None
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.read_bytes())
    else:
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
    return h.hexdigest()

def kill_port(port=PORT):
    try:
        pids = subprocess.getoutput(f"lsof -ti:{port}").splitlines()
        for pid in pids:
            subprocess.run(["kill", "-9", pid])
            log(f"⏹️ Killed process {pid} on port {port}")
    except Exception as e:
        log(f"⚠️ Error killing port {port}: {e}")

def check_files():
    missing = [f for f in CRITICAL_FILES if not Path(f).exists()]
    if missing:
        log(f"⚠️ Missing critical files: {missing}")
    else:
        log("✅ All critical files exist.")

def check_secrets():
    missing = [s for s in CRITICAL_SECRETS if not Path(s).exists()]
    if missing:
        log(f"⚠️ Missing secrets: {missing}")
    else:
        log("✅ All secrets exist.")

def ensure_python():
    python_path = Path(sys.executable)
    log(f"🔹 Using Python at {python_path}")
    return python_path

# --------------------------
# Run Gunicorn
# --------------------------
def run_app(python_path):
    global APP_PROCESS, STATUS
    kill_port(PORT)
    if APP_PROCESS and APP_PROCESS.poll() is None:
        log(f"🔹 Gunicorn already running (PID {APP_PROCESS.pid})")
        return
    if not Path("app.py").exists():
        log("❌ app.py not found, cannot start Gunicorn")
        return
    STATUS = "STARTING"
    APP_PROCESS = subprocess.Popen([
        str(python_path), "-m", "gunicorn", "--workers", "4", "--bind",
        f"0.0.0.0:{PORT}", "app:app"
    ])
    time.sleep(1)
    STATUS = "ONLINE"
    log(f"✅ Server started on port {PORT} (PID {APP_PROCESS.pid})")

# --------------------------
# Cleanup
# --------------------------
def cleanup():
    global APP_PROCESS, STATUS
    STATUS = "SHUTTING DOWN"
    if APP_PROCESS:
        log("⏹️ Terminating Gunicorn...")
        APP_PROCESS.terminate()
    STATUS = "OFFLINE"

atexit.register(cleanup)

# --------------------------
# Git & Deploy
# --------------------------
def git_commit_push():
    secrets_paths = [str(s) for s in CRITICAL_SECRETS] + [str(SERVICE_ACCOUNT_PATH)]
    all_files = subprocess.getoutput("git ls-files").splitlines()
    files_to_add = [f for f in all_files if f not in secrets_paths]
    if files_to_add:
        run(["git", "add"] + files_to_add, silent=True)
    run(["git", "commit", "-m", "Auto deploy commit", "--allow-empty"], silent=True)
    if GITHUB_TOKEN:
        run([
            "git", "push", "--set-upstream",
            f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", "main"
        ], silent=True)
        log("✅ Git push done (secrets excluded)")
    else:
        log("⚠️ GITHUB_TOKEN missing, skipping Git push")

def deploy_vercel():
    global VERCEL_URL
    if not VERCEL_TOKEN or shutil.which("vercel") is None:
        log("⚠️ Vercel token missing or CLI not found, skipping deploy")
        return
    STATUS = "DEPLOYING"
    run(["vercel", "--prod", "--yes", "--token", VERCEL_TOKEN], silent=True)
    # ดึง URL ล่าสุดจาก Vercel CLI
    try:
        url = subprocess.getoutput(f"vercel --prod --token {VERCEL_TOKEN} --confirm | grep -o 'https://.*'").strip()
        VERCEL_URL = url if url else VERCEL_URL
    except:
        pass
    log(f"✅ Deployed to Vercel at: {VERCEL_URL or 'URL unknown'}")
    STATUS = "ONLINE"

def deploy_firebase():
    global FIREBASE_URL
    if not SERVICE_ACCOUNT_PATH.exists() or shutil.which("firebase") is None:
        log("⚠️ Firebase Service Account or Firebase CLI missing, skipping deploy")
        return
    STATUS = "DEPLOYING"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(SERVICE_ACCOUNT_PATH.resolve())
    run([
        "firebase", "deploy", "--only", "hosting", "--project", FIREBASE_PROJECT
    ], silent=True)
    FIREBASE_URL = f"https://{FIREBASE_PROJECT}.web.app"
    log(f"✅ Deployed to Firebase at: {FIREBASE_URL}")
    STATUS = "ONLINE"

# --------------------------
# Watchdog
# --------------------------
FILE_HASHES = {}

class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        global FILE_HASHES, STATUS
        for f in CRITICAL_FILES:
            h = file_hash(f)
            if FILE_HASHES.get(f) != h:
                FILE_HASHES[f] = h
                log("🔹 Changes detected: committing, deploying, restarting app...")
                STATUS = "DEPLOYING"
                git_commit_push()
                deploy_vercel()
                deploy_firebase()
                run_app(Path(sys.executable))
                STATUS = "ONLINE"
                break

def watch_files():
    observer = Observer()
    observer.schedule(ChangeHandler(), ".", recursive=True)
    observer.start()
    return observer

# --------------------------
# Stop command listener
# --------------------------
def listen_stop_commands():
    global STATUS
    while True:
        try:
            cmd = input().strip()
            if cmd.lower() in ["เลิกงาน", "หยุดทำงาน", "stop", "exit", "quit"]:
                log("🛑 Stop command received. Shutting down...")
                STATUS = "SHUTTING DOWN"
                cleanup()
                os._exit(0)
        except EOFError:
            time.sleep(1)

# --------------------------
# Main loop
# --------------------------
def main_loop():
    python_path = ensure_python()
    check_files()
    check_secrets()
    run_app(python_path)

    threading.Thread(target=hud_animation, daemon=True).start()
    observer = watch_files()
    threading.Thread(target=listen_stop_commands, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    cleanup()

if __name__ == "__main__":
    main_loop()
