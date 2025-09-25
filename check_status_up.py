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

if __name__ == "__main__":
    main()
