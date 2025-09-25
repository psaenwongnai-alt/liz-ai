<<<<<<< Updated upstream
# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

# --------------------------
# Config
# --------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "psaenwongnai-alt/liz-ai"
FIREBASE_JSON = os.environ.get("FIREBASE_CONFIG_JSON")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
CHECK_INTERVAL = 30  # วินาที ตรวจสอบไฟล์สำคัญ
LOG_FILE = "deploy_history.log"

# ไฟล์สำคัญ
CRITICAL_FILES = [
    "app.py",
    "check_status_up.py",
    "requirements.txt",
    "templates/index.html",
]

# ตัวอย่าง environment / secret
CRITICAL_SECRETS = [
    ".env",
]

PRESERVE_FILES = CRITICAL_FILES.copy()
EXCLUDE_EXT = [".json", ".env"]
BACKUP_LIMIT = 5

# --------------------------
# Logging
# --------------------------
def log(msg):
    print(f"[{datetime.now().isoformat()}] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")

# --------------------------
# Helper functions
# --------------------------
def run(cmd, **kwargs):
    return subprocess.run(cmd, shell=False, check=True, **kwargs)

def git_checkout_branch(branch):
    run(["git", "checkout", "-B", branch])

def git_add_commit_push(files, branch, message="Auto commit"):
    if not files:
        return
    run(["git", "add"] + files)
    run(["git", "commit", "-m", message])
    run(["git", "push", "--force", GITHUB_TOKEN, f"{branch}:main"])

def backup_branch():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    branch = f"backup_before_deploy_{timestamp}"
    try:
        git_checkout_branch(branch)
        run(["git", "push", "--set-upstream", f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", branch])
        log(f"💾 Backup branch created: {branch}")
    except subprocess.CalledProcessError as e:
        log(f"⚠️ Backup failed: {e}")
    return branch

def clean_old_backups():
    branches = subprocess.run(["git", "branch"], capture_output=True, text=True).stdout.splitlines()
    branches = [b.strip().replace("* ", "") for b in branches if "backup_before_deploy_" in b]
    branches.sort()
    if len(branches) > BACKUP_LIMIT:
        for old_branch in branches[:-BACKUP_LIMIT]:
            subprocess.run(["git", "branch", "-D", old_branch])
            subprocess.run(["git", "push", f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", f":{old_branch}"])
            log(f"🗑️ Deleted old backup branch: {old_branch}")

def reset_tmp_branch(tmp_branch):
    git_checkout_branch(tmp_branch)
    for f in Path(".").glob("*"):
        if f.name not in PRESERVE_FILES:
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)
    run(["git", "commit", "--allow-empty", "-m", "Reset tmp branch"])
    log("🗑️ Temporary branch reset for deploy")

# --------------------------
# Self-healing
# --------------------------
def restore_missing_files():
    restored = []
    # Restore critical files
    for f in CRITICAL_FILES:
        if not Path(f).exists():
            try:
                run(["git", "checkout", "origin/main", "--", f])
                restored.append(f)
            except subprocess.CalledProcessError:
                log(f"❌ Failed to restore {f}")

    # Restore secrets / .env
    restored_secrets = []
    for s in CRITICAL_SECRETS:
        if not Path(s).exists() and Path(f"{s}.example").exists():
            shutil.copy(f"{s}.example", s)
            restored_secrets.append(s)

    if restored or restored_secrets:
        log(f"✅ Restored files: {restored + restored_secrets}")
        git_add_commit_push(restored + restored_secrets, "main", message="Restore critical files & secrets")

    # Restore requirements
    if "requirements.txt" in restored:
        try:
            run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            log("✅ requirements.txt restored & dependencies installed")
        except subprocess.CalledProcessError as e:
            log(f"❌ Failed to install dependencies: {e}")

# --------------------------
# Vercel deploy
# --------------------------
def deploy_vercel():
    try:
        run(["vercel", "--version"])
    except FileNotFoundError:
        log("❌ Vercel CLI not found. Run: npm install -g vercel")
        return
    try:
        run(["vercel", "--prod", "--confirm"])
        log("✅ Deployment to Vercel complete")
    except subprocess.CalledProcessError as e:
        log(f"❌ Deployment failed: {e}")

# --------------------------
# Full deploy
# --------------------------
def full_deploy_pipeline():
    log("🚀 Starting full deploy pipeline...")
    backup_branch()
    clean_old_backups()
    tmp_branch = f"tmp_deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    reset_tmp_branch(tmp_branch)
=======
import os
import subprocess
import datetime
import sys

REPO = "https://github.com/psaenwongnai-alt/liz-ai.git"
BRANCH = "main"
RESTORE_FILES = [
    "requirements.txt",
    "app.py",
    "templates/index.html",
    "static/"
]

def log(msg):
    ts = datetime.datetime.utcnow().strftime("[%Y-%m-%d %H:%M:%S]")
    print(ts, msg)
    with open("deploy_history.log", "a") as f:
        f.write(ts + " " + msg + "\n")

def run(cmd, check=True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def ensure_git():
    if not os.path.isdir(".git"):
        log("⚙️ No .git found → init new repo")
        run(["git", "init"])
        run(["git", "remote", "add", "origin", REPO])
        run(["git", "fetch", "origin"])
        run(["git", "checkout", "-b", BRANCH, "origin/main"])
    else:
        run(["git", "fetch", "origin"])
        run(["git", "stash", "push", "-m", "auto-stash-before-checkout"], check=False)
        run(["git", "checkout", "-B", BRANCH, "origin/main"])
        run(["git", "stash", "pop"], check=False)

def backup_branch():
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_before_deploy_{ts}"
    run(["git", "checkout", "-b", backup_name])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"Backup before deploy {ts}"])
    run(["git", "push", "origin", backup_name])
    log(f"💾 Backup branch created: {backup_name}")

def restore_files():
    restored = []
    for f in RESTORE_FILES:
        try:
            run(["git", "checkout", BRANCH, "--", f], check=False)
            restored.append(f)
        except Exception:
            log(f"⚠️ Failed to restore {f}")
    if restored:
        log(f"✅ Restored files: {restored}")

def install_requirements():
    if os.path.exists("requirements.txt"):
        log("📦 Installing dependencies...")
        run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=False)

def main():
    log("🚀 Starting full deploy pipeline (ultimate mode)...")
    ensure_git()
    backup_branch()
    restore_files()
    install_requirements()
    log("✨ Deploy pipeline finished successfully!")
>>>>>>> Stashed changes

    # Add files (ไม่รวม secrets)
    files_to_add = [str(f) for f in Path(".").iterdir() if f.name not in EXCLUDE_EXT + PRESERVE_FILES]
    git_add_commit_push(files_to_add, tmp_branch, message="Deploy new version")

    # Push tmp branch to main
    try:
        run(["git", "push", "--force", f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git", f"{tmp_branch}:main"])
        log("✅ Push to GitHub main complete")
    except subprocess.CalledProcessError as e:
        log(f"❌ Push failed: {e}")

    deploy_vercel()
    log("🎉 Deploy pipeline finished successfully!")

# --------------------------
# Main loop
# --------------------------
if __name__ == "__main__":
    while True:
        try:
            restore_missing_files()
            full_deploy_pipeline()
        except Exception as e:
            log(f"❌ Unexpected error: {e}")
        log(f"⏳ Sleeping {CHECK_INTERVAL}s before next check...")
        time.sleep(CHECK_INTERVAL)
