# -*- coding: utf-8 -*-
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import sys
import time
import venv

# --------------------------
# Config
# --------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "psaenwongnai-alt/liz-ai"
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
FIREBASE_TOKEN = os.environ.get("FIREBASE_TOKEN")

CHECK_INTERVAL = 30
LOG_FILE = "deploy_history.log"

CRITICAL_FILES = [
    "app.py",
    "requirements.txt",
    "templates/index.html",
    "static",
]

CRITICAL_SECRETS = [
    ".env",
]

VENV_DIR = Path(".venv")
APP_PROCESS = None  # handle subprocess


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


# --------------------------
# Git helpers
# --------------------------
def ensure_git():
    if not Path(".git").exists():
        run(["git", "init"])
        run([
            "git", "remote", "add", "origin",
            f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
        ])
    try:
        run(["git", "fetch", "origin"])
        run(["git", "stash", "push", "-m", "auto-stash"])
        run(["git", "checkout", "-B", "main", "origin/main"])
        run(["git", "stash", "pop"])
    except subprocess.CalledProcessError:
        log("⚠️ Cannot checkout main from origin/main, maybe empty repo.")


def git_commit_push(message="Auto deploy commit"):
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", message, "--allow-empty"])
    run([
        "git", "push", "--set-upstream",
        f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", "main"
    ])
    log("✅ Git push done")


# --------------------------
# Restore files
# --------------------------
def restore_files():
    restored = []
    for f in CRITICAL_FILES:
        path = Path(f)
        if not path.exists():
            try:
                run(["git", "checkout", "origin/main", "--", f])
                restored.append(f)
            except subprocess.CalledProcessError:
                if path.suffix == ".py":
                    path.write_text("# default placeholder\n")
                elif path.name == "requirements.txt":
                    path.write_text("flask\n")
                elif path.name == "index.html":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        "<!DOCTYPE html>\n<html><head></head><body></body></html>"
                    )
                else:
                    path.mkdir(parents=True, exist_ok=True)
                restored.append(f)
    if restored:
        log(f"✅ Restored/created files: {restored}")


def restore_secrets():
    restored = []
    for s in CRITICAL_SECRETS:
        path = Path(s)
        example_path = Path(f"{s}.example")
        if not path.exists() and example_path.exists():
            shutil.copy(example_path, path)
            restored.append(s)
    if restored:
        log(f"✅ Restored secrets: {restored}")


# --------------------------
# Virtual environment + dependencies
# --------------------------
def ensure_venv():
    if not VENV_DIR.exists():
        log("🔹 Creating virtual environment...")
        venv.create(VENV_DIR, with_pip=True)
    pip_path = VENV_DIR / "bin" / "pip"
    python_path = VENV_DIR / "bin" / "python"
    if Path("requirements.txt").exists():
        log("🔹 Installing dependencies in virtualenv...")
        run([str(pip_path), "install", "-r", "requirements.txt"])
    return python_path


# --------------------------
# Run app.py
# --------------------------
def run_app(python_path):
    global APP_PROCESS
    if APP_PROCESS and APP_PROCESS.poll() is None:
        log("🔹 app.py already running, skipping start")
        return
    if Path("app.py").exists():
        log("🔹 Starting app.py in background...")
        APP_PROCESS = subprocess.Popen([str(python_path), "app.py"])
        log(f"✅ app.py started with PID {APP_PROCESS.pid}")
    else:
        log("⚠️ app.py not found, cannot start")


# --------------------------
# Deploy
# --------------------------
def deploy_vercel():
    if not VERCEL_TOKEN:
        log("⚠️ VERCEL_TOKEN not set, skipping deploy")
        return
    if shutil.which("vercel") is None:
        log("⚠️ Vercel CLI not found, skipping deploy")
        return
    run(["vercel", "--prod", "--yes", "--token", VERCEL_TOKEN])
    log("✅ Deployed to Vercel")


def deploy_firebase():
    if not FIREBASE_TOKEN:
        log("⚠️ FIREBASE_TOKEN not set, skipping deploy")
        return
    if shutil.which("firebase") is None:
        log("⚠️ Firebase CLI not found, skipping deploy")
        return
    run(["firebase", "deploy", "--only", "hosting", "--token", FIREBASE_TOKEN])
    log("✅ Deployed to Firebase")


# --------------------------
# Main loop
# --------------------------
def main_loop():
    python_path = ensure_venv()
    while True:
        try:
            ensure_git()
            restore_files()
            restore_secrets()
            run_app(python_path)
            git_commit_push()
            deploy_vercel()
            deploy_firebase()
        except Exception as e:
            log(f"❌ Unexpected error: {e}")
        log(f"⏳ Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


# --------------------------
# Run
# --------------------------
if __name__ == "__main__":
    main_loop()
