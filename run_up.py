# -*- coding: utf-8 -*-
import os, subprocess, shutil, time, venv, atexit, hashlib
from pathlib import Path
from datetime import datetime

# --------------------------
# Config
# --------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "psaenwongnai-alt/liz-ai"
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
SERVICE_ACCOUNT_PATH = Path("secrets/firebase-service-account.json")
FIREBASE_PROJECT = "liz-ai-project"

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
APP_PROCESS = None
FILE_HASHES = {}


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
# Restore files & secrets
# --------------------------
def restore_files():
    restored = []
    for f in CRITICAL_FILES:
        path = Path(f)
        if not path.exists():
            if f == "static":
                path.mkdir(parents=True, exist_ok=True)
            elif path.suffix == ".py":
                path.write_text("# default placeholder\n")
            elif path.name == "requirements.txt":
                path.write_text("flask\n")
            elif path.name == "index.html":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "<!DOCTYPE html>\n<html><head></head><body></body></html>")
            restored.append(f)
    if restored:
        log(f"✅ Restored/created files: {restored}")


def restore_secrets():
    for s in CRITICAL_SECRETS:
        path = Path(s)
        example_path = Path(f"{s}.example")
        if not path.exists() and example_path.exists():
            shutil.copy(example_path, path)
            log(f"✅ Restored secret: {s}")


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
    try:
        run(["vercel", "--prod", "--yes", "--token", VERCEL_TOKEN])
        log("✅ Deployed to Vercel")
    except Exception as e:
        log(f"❌ Vercel deploy failed: {e}")


def deploy_firebase():
    if not SERVICE_ACCOUNT_PATH.exists() or shutil.which("firebase") is None:
        log("⚠️ Firebase Service Account or Firebase CLI missing, skipping deploy"
            )
        return
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
        SERVICE_ACCOUNT_PATH.resolve())
    try:
        run([
            "firebase", "deploy", "--only", "hosting", "--project",
            FIREBASE_PROJECT
        ])
        log("✅ Deployed to Firebase")
    except Exception as e:
        log(f"❌ Firebase deploy failed: {e}")


# --------------------------
# Main smart loop
# --------------------------
def main_loop():
    python_path = ensure_venv()
    while True:
        try:
            restore_files()
            restore_secrets()
            run_app(python_path)

            # --------------------------
            # Check for changes
            # --------------------------
            changed = False
            for f in CRITICAL_FILES:
                h = file_hash(f)
                if FILE_HASHES.get(f) != h:
                    FILE_HASHES[f] = h
                    changed = True

            if changed:
                log("🔹 Changes detected, committing and deploying...")
                git_commit_push()
                deploy_vercel()
                deploy_firebase()
            else:
                log("⏹️ No changes detected, skipping deploy")

        except Exception as e:
            log(f"❌ Unexpected error: {e}")

        log(f"⏳ Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main_loop()
