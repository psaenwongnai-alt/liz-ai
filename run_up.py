# -*- coding: utf-8 -*-
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import sys
import time

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
    return subprocess.run(cmd, shell=False, check=True, **kwargs)


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
        # stash ก่อน checkout ป้องกัน overwrite
        run(["git", "stash", "push", "-m", "auto-stash"])
        run(["git", "checkout", "-B", "main", "origin/main"])
        run(["git", "stash", "pop"])
    except subprocess.CalledProcessError:
        log("⚠️ Cannot checkout main from origin/main, maybe empty repo.")


def git_commit_push(message="Auto deploy commit"):
    try:
        run(["git", "add", "-A"])
        run(["git", "commit", "-m", message, "--allow-empty"])
        run([
            "git", "push", "--set-upstream",
            f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", "main"
        ])
        log("✅ Pushed to GitHub")
    except subprocess.CalledProcessError as e:
        log(f"❌ Git push failed: {e}")


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
                # สร้าง default ถ้าไม่มี
                if path.suffix == ".py":
                    path.write_text("# default placeholder\n")
                elif path.name == "requirements.txt":
                    path.write_text("flask\n")
                elif path.name == "templates/index.html":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        "<!DOCTYPE html>\n<html><head></head><body></body></html>"
                    )
                elif path.name == "static":
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
        log(f"✅ Restored secrets from examples: {restored}")


# --------------------------
# Dependencies
# --------------------------
def install_dependencies():
    req_file = Path("requirements.txt")
    if req_file.exists():
        try:
            if "/nix/store" in sys.executable:
                log("⚠️ Skipping pip install on Nix environment")
                return
            run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
            log("✅ Dependencies installed")
        except subprocess.CalledProcessError as e:
            log(f"❌ Failed to install dependencies: {e}")


# --------------------------
# Deploy
# --------------------------
def deploy_vercel():
    if VERCEL_TOKEN:
        try:
            run(["vercel", "--version"])
            run(["vercel", "--prod", "--confirm"])
            log("✅ Deployed to Vercel")
        except FileNotFoundError:
            log("⚠️ Vercel CLI not found, skipping deploy")
        except subprocess.CalledProcessError as e:
            log(f"❌ Vercel deploy failed: {e}")


def deploy_firebase():
    if FIREBASE_TOKEN:
        try:
            run(["firebase", "--version"])
            run(["firebase", "deploy", "--only", "hosting"])
            log("✅ Deployed to Firebase")
        except FileNotFoundError:
            log("⚠️ Firebase CLI not found, skipping deploy")
        except subprocess.CalledProcessError as e:
            log(f"❌ Firebase deploy failed: {e}")


# --------------------------
# Main loop
# --------------------------
def main_loop():
    while True:
        try:
            ensure_git()
            restore_files()
            restore_secrets()
            install_dependencies()
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
