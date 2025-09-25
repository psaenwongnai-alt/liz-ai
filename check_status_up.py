# -*- coding: utf-8 -*-
import os, subprocess, shutil, sys, time, json, threading
from pathlib import Path
from datetime import datetime

# --------------------------
# Config
# --------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "psaenwongnai-alt/liz-ai"
FIREBASE_JSON = os.environ.get("FIREBASE_JSON")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")

CHECK_INTERVAL = 30  # วินาที ตรวจสอบไฟล์
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

# --------------------------
# Logging
# --------------------------
def log(msg):
    print(f"[{datetime.now()}] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

# --------------------------
# Helper
# --------------------------
def run(cmd, **kwargs):
    return subprocess.run(cmd, shell=False, check=True, **kwargs)

# --------------------------
# Git helpers
# --------------------------
def ensure_git():
    if not (Path(".git").exists()):
        run(["git", "init"])
        run(["git", "remote", "add", "origin",
             f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"])
    try:
        run(["git", "fetch", "origin"])
        run(["git", "checkout", "-B", "main", "origin/main"])
    except subprocess.CalledProcessError:
        log("⚠️ Cannot checkout main from origin/main. GitHub may be empty.")
        run(["git", "checkout", "-B", "main"])

def git_commit_push(msg="Auto commit"):
    run(["git", "add", "-A"])
    try:
        run(["git", "commit", "-m", msg])
    except subprocess.CalledProcessError:
        pass
    try:
        run(["git", "push", "--set-upstream",
             f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", "main"])
        log("✅ Pushed to GitHub")
    except subprocess.CalledProcessError as e:
        log(f"❌ Push to GitHub failed: {e}")

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
                    path.write_text("flask>=3.1.2\n")
                elif path.name == "templates/index.html":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("<!DOCTYPE html><html><head></head><body></body></html>")
                elif path.name == "static":
                    path.mkdir(parents=True, exist_ok=True)
                restored.append(f)
    if restored:
        log(f"✅ Restored or created files: {restored}")

def restore_secrets():
    restored = []
    for s in CRITICAL_SECRETS:
        path = Path(s)
        example_path = Path(f"{s}.example")
        if not path.exists() and example_path.exists():
            shutil.copy(example_path, path)
            restored.append(s)
    if restored:
        log(f"✅ Restored secrets from examples: {restored}")

def install_dependencies():
    req_file = Path("requirements.txt")
    if req_file.exists():
        try:
            run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
            log("✅ Dependencies installed")
        except subprocess.CalledProcessError as e:
            log(f"❌ Failed to install dependencies: {e}")

# --------------------------
# Deploy functions
# --------------------------
def deploy_vercel():
    if VERCEL_TOKEN:
        try:
            run(["vercel", "--version"])
            run(["vercel", "--prod", "--confirm"])
            log("✅ Deployed to Vercel")
        except FileNotFoundError:
            log("⚠️ Vercel CLI not found")
        except subprocess.CalledProcessError as e:
            log(f"❌ Vercel deploy failed: {e}")

def deploy_firebase():
    if FIREBASE_JSON:
        try:
            firebase_path = Path("firebase_temp.json")
            firebase_path.write_text(FIREBASE_JSON)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(firebase_path)

            run(["firebase", "--version"])
            run(["firebase", "deploy", "--only", "hosting", "--token", FIREBASE_JSON])
            log("✅ Deployed to Firebase Hosting")
        except FileNotFoundError:
            log("⚠️ Firebase CLI not found")
        except subprocess.CalledProcessError as e:
            log(f"❌ Firebase deploy failed: {e}")
        finally:
            if firebase_path.exists():
                firebase_path.unlink()

# --------------------------
# Main loop (with async deploy)
# --------------------------
def main_loop():
    while True:
        try:
            ensure_git()
            restore_files()
            restore_secrets()
            install_dependencies()
            git_commit_push("Auto deploy from check_status_up.py")

            # Deploy async
            threads = []
            t1 = threading.Thread(target=deploy_vercel)
            t2 = threading.Thread(target=deploy_firebase)
            threads.extend([t1, t2])
            for t in threads: t.start()
            for t in threads: t.join()

        except Exception as e:
            log(f"❌ Unexpected error: {e}")
        log(f"⏳ Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
