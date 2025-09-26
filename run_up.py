# -*- coding: utf-8 -*-
import os, subprocess, shutil, time, atexit, hashlib, sys
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
    "app.py", "requirements.txt", "templates/index.html", "static/style.css",
    "static/script.js", "static/icon.png", "static/ting.mp3"
]
CRITICAL_SECRETS = [".env"]
APP_PROCESS = None


# --------------------------
# Logging
# --------------------------
def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")


# --------------------------
# Helper
# --------------------------
def run(cmd, silent=False):
    try:
        if silent:
            subprocess.run(cmd,
                           check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
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


# --------------------------
# Check files/secrets
# --------------------------
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


# --------------------------
# Use current Python
# --------------------------
def ensure_python():
    python_path = Path(sys.executable)  # ใช้ Python ที่รัน script นี้
    log(f"🔹 Using Python at {python_path}")
    return python_path


# --------------------------
# Run Gunicorn
# --------------------------
def run_app(python_path):
    global APP_PROCESS
    if APP_PROCESS and APP_PROCESS.poll() is None:
        log(f"🔹 Gunicorn already running (PID {APP_PROCESS.pid})")
        return
    if not Path("app.py").exists():
        log("❌ app.py not found, cannot start Gunicorn")
        return
    port = os.environ.get("PORT", "3000")
    APP_PROCESS = subprocess.Popen([
        str(python_path), "-m", "gunicorn", "--workers", "4", "--bind",
        f"0.0.0.0:{port}", "app:app"
    ],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    log(f"✅ Gunicorn started on port {port} (PID {APP_PROCESS.pid})")


def cleanup():
    global APP_PROCESS
    if APP_PROCESS:
        log("⏹️ Terminating Gunicorn...")
        APP_PROCESS.terminate()


atexit.register(cleanup)


# --------------------------
# Git push excluding secrets
# --------------------------
def git_commit_push():
    secrets_paths = [str(s)
                     for s in CRITICAL_SECRETS] + [str(SERVICE_ACCOUNT_PATH)]
    all_files = subprocess.getoutput("git ls-files").splitlines()
    files_to_add = [f for f in all_files if f not in secrets_paths]
    if files_to_add:
        run(["git", "add"] + files_to_add, silent=True)
    run(["git", "commit", "-m", "Auto deploy commit", "--allow-empty"],
        silent=True)
    if GITHUB_TOKEN:
        run([
            "git", "push", "--set-upstream",
            f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", "main"
        ],
            silent=True)
        log("✅ Git push done (secrets excluded)")
    else:
        log("⚠️ GITHUB_TOKEN missing, skipping Git push")


# --------------------------
# Deploy
# --------------------------
def deploy_vercel():
    if not VERCEL_TOKEN or shutil.which("vercel") is None:
        log("⚠️ Vercel token missing or CLI not found, skipping deploy")
        return
    run(["vercel", "--prod", "--yes", "--token", VERCEL_TOKEN], silent=True)
    log("✅ Deployed to Vercel")


def deploy_firebase():
    if not SERVICE_ACCOUNT_PATH.exists() or shutil.which("firebase") is None:
        log("⚠️ Firebase Service Account or Firebase CLI missing, skipping deploy"
            )
        return
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
        SERVICE_ACCOUNT_PATH.resolve())
    run([
        "firebase", "deploy", "--only", "hosting", "--project",
        FIREBASE_PROJECT
    ],
        silent=True)
    log("✅ Deployed to Firebase")


# --------------------------
# Watchdog
# --------------------------
FILE_HASHES = {}


class ChangeHandler(FileSystemEventHandler):

    def on_modified(self, event):
        global FILE_HASHES
        for f in CRITICAL_FILES:
            h = file_hash(f)
            if FILE_HASHES.get(f) != h:
                FILE_HASHES[f] = h
                log("🔹 Changes detected: committing, deploying, restarting app..."
                    )
                git_commit_push()
                deploy_vercel()
                deploy_firebase()
                run_app(Path(sys.executable))
                break


def watch_files():
    observer = Observer()
    observer.schedule(ChangeHandler(), ".", recursive=True)
    observer.start()
    return observer


# --------------------------
# Main
# --------------------------
def main_loop():
    python_path = ensure_python()
    check_files()
    check_secrets()
    run_app(python_path)
    observer = watch_files()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    cleanup()


if __name__ == "__main__":
    main_loop()
