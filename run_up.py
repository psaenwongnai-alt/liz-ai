# -*- coding: utf-8 -*-
import os, subprocess, shutil, time, venv, atexit, hashlib
from pathlib import Path
from datetime import datetime
from threading import Thread

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

VENV_DIR = Path(".venv")
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
def run(cmd, **kwargs):
    try:
        return subprocess.run(cmd, shell=False, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        log(f"❌ Command failed: {cmd} -> {e}")
        return None


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
# Check critical files
# --------------------------
def check_files():
    missing_files = [f for f in CRITICAL_FILES if not Path(f).exists()]
    if missing_files:
        log(f"⚠️ Missing critical files (cannot run app properly): {missing_files}"
            )
    else:
        log("✅ All critical files exist.")


def check_secrets():
    missing_secrets = [s for s in CRITICAL_SECRETS if not Path(s).exists()]
    if missing_secrets:
        log(f"⚠️ Missing secrets (app may fail): {missing_secrets}")
    else:
        log("✅ All secrets exist.")


# --------------------------
# Firebase config
# --------------------------
def ensure_firebase():
    firebase_json = Path("firebase.json")
    public_dir = Path("public")
    index_html = public_dir / "index.html"

    if not firebase_json.exists():
        firebase_json.write_text("""{
  "hosting": {
    "public": "public",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [ { "source": "**", "destination": "/index.html" } ]
  }
}""")
        log("✅ Created default firebase.json")

    if not public_dir.exists():
        public_dir.mkdir(parents=True)
        log("✅ Created public/ folder")

    if not index_html.exists():
        index_html.write_text(
            "<!DOCTYPE html><html><head></head><body></body></html>")
        log("✅ Created public/index.html")


# --------------------------
# Virtualenv
# --------------------------
def ensure_venv():
    if not VENV_DIR.exists():
        log("🔹 Creating virtual environment...")
        venv.create(VENV_DIR, with_pip=True)
    pip_path = VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / "pip"
    python_path = VENV_DIR / ("Scripts"
                              if os.name == "nt" else "bin") / "python"
    if Path("requirements.txt").exists():
        log("🔹 Installing dependencies in virtualenv...")
        run([str(pip_path), "install", "-r", "requirements.txt"])
    return python_path


# --------------------------
# App process
# --------------------------
def run_app(python_path):
    global APP_PROCESS
    if APP_PROCESS and APP_PROCESS.poll() is None:
        return
    if Path("app.py").exists():
        APP_PROCESS = subprocess.Popen([str(python_path), "app.py"])
        log(f"✅ app.py started with PID {APP_PROCESS.pid}")


def cleanup():
    global APP_PROCESS
    if APP_PROCESS:
        log("⏹️ Terminating app.py...")
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
        run(["git", "add"] + files_to_add)
    run(["git", "commit", "-m", "Auto deploy commit", "--allow-empty"])
    run([
        "git", "push", "--set-upstream",
        f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", "main"
    ])
    log("✅ Git push done (secrets excluded)")


# --------------------------
# Deploy
# --------------------------
def deploy_vercel():
    if not VERCEL_TOKEN or shutil.which("vercel") is None:
        log("⚠️ Vercel token missing or CLI not found, skipping deploy")
        return
    run(["vercel", "--prod", "--yes", "--token", VERCEL_TOKEN])
    log("✅ Deployed to Vercel")


def deploy_firebase():
    ensure_firebase()
    if not SERVICE_ACCOUNT_PATH.exists() or shutil.which("firebase") is None:
        log("⚠️ Firebase Service Account or Firebase CLI missing, skipping deploy"
            )
        return
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
        SERVICE_ACCOUNT_PATH.resolve())
    run([
        "firebase", "deploy", "--only", "hosting", "--project",
        FIREBASE_PROJECT
    ])
    log("✅ Deployed to Firebase")


# --------------------------
# Watch for changes
# --------------------------
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    subprocess.run([str(Path(".venv/bin/pip")), "install", "watchdog"])
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

FILE_HASHES = {}


class ChangeHandler(FileSystemEventHandler):

    def on_modified(self, event):
        global FILE_HASHES
        for f in CRITICAL_FILES:
            h = file_hash(f)
            if FILE_HASHES.get(f) != h:
                FILE_HASHES[f] = h
                log("🔹 Changes detected, committing and deploying...")
                git_commit_push()
                deploy_vercel()
                deploy_firebase()
                run_app(VENV_DIR / ("Scripts" if os.name == "nt" else "bin") /
                        "python")
                break


def watch_files():
    observer = Observer()
    observer.schedule(ChangeHandler(), ".", recursive=True)
    observer.start()
    return observer


# --------------------------
# Main loop
# --------------------------
def main_loop():
    python_path = ensure_venv()
    check_files()
    check_secrets()
    ensure_firebase()
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
