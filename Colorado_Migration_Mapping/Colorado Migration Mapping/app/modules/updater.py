"""
In-app updater.

Downloads the latest code archive from the git server (Gitea or GitHub),
copies it over this install, reinstalls Python packages if requirements.txt
changed, then relaunches the server. No git client needed on the user's
machine -- it only needs network access to the git server.

What is NEVER touched (same rules as Update.bat):
    environment_data/   the ~19 GB elevation / snow / road data
    app/session_data/   saved sessions
    python-3.13/        the bundled interpreter + installed packages

Configuration: edit DEFAULTS below, or drop an update_config.json next to
Start App.bat with any of the same keys, e.g.

    {"repo_url": "https://host/git/Owner/Repo.git", "branch": "main",
     "token": "", "verify_ssl": true}
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent          # .../app
ROOT = _APP.parent                                      # .../Colorado Migration Mapping

DEFAULTS = {
    # Internal Gitea (see deploy.sh). Switch to the GitHub URL if preferred.
    "repo_url": "https://dnrapp110.naturenet.state.co.us/git/ShinyDev/MigrationAnalyzer.git",
    "branch": "main",
    "token": "",            # personal access token if the repo is private
    "verify_ssl": True,     # set false for an internal server with a self-signed cert
}
CONFIG_FILE = ROOT / "update_config.json"
VERSION_FILE = ROOT / ".installed_version"

# Top-level folders in the install that an update must never overwrite.
PROTECTED_DIRS = {"environment_data", "python-3.13", "session_data", "__pycache__"}
PROTECTED_PREFIX = "_backup_"

_lock = threading.Lock()
_status: dict = {
    "state": "idle",        # idle | checking | available | uptodate | updating | restarting | error
    "message": "",
    "log": [],
    "local_sha": None,
    "remote_sha": None,
    "remote_date": None,
}


# ---------------------------------------------------------------------------
# Config / helpers
# ---------------------------------------------------------------------------
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.is_file():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            _log(f"Could not read update_config.json ({exc}); using defaults.")
    return cfg


def _parse_repo(repo_url: str) -> tuple[str, str, str, str]:
    """Return (kind, base, owner, repo). kind is 'github' or 'gitea'."""
    url = repo_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    scheme, rest = url.split("://", 1)
    parts = rest.split("/")
    host = parts[0]
    owner, repo = parts[-2], parts[-1]
    base = scheme + "://" + "/".join(parts[:-2])
    kind = "github" if host.lower().endswith("github.com") else "gitea"
    return kind, base, owner, repo


def _urls(cfg: dict) -> dict:
    kind, base, owner, repo = _parse_repo(cfg["repo_url"])
    branch = cfg["branch"]
    if kind == "github":
        return {
            "kind": kind,
            "archive": f"{base}/{owner}/{repo}/archive/refs/heads/{branch}.zip",
            "latest": f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}",
        }
    return {
        "kind": kind,
        "archive": f"{base}/{owner}/{repo}/archive/{branch}.zip",
        "latest": f"{base}/api/v1/repos/{owner}/{repo}/branches/{branch}",
    }


def _open(url: str, cfg: dict, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "MigrationCorridorMapper-updater"})
    tok = cfg.get("token") or ""
    if tok:
        req.add_header("Authorization", ("Bearer " if _urls(cfg)["kind"] == "github" else "token ") + tok)
    ctx = None
    if not cfg.get("verify_ssl", True):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def _log(line: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    with _lock:
        _status["log"].append(f"[{stamp}] {line}")
        _status["log"] = _status["log"][-200:]
    print(f"[updater] {line}", flush=True)


def _set(**kw) -> None:
    with _lock:
        _status.update(kw)


def get_status() -> dict:
    with _lock:
        return {**_status, "log": list(_status["log"])}


def local_version() -> str | None:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------
def check_for_update() -> dict:
    """Synchronous. Asks the server for the latest commit on the branch."""
    cfg = load_config()
    urls = _urls(cfg)
    _set(state="checking", message="Checking for updates...", local_sha=local_version())
    _log(f"Checking {cfg['repo_url']} ({cfg['branch']})")
    try:
        with _open(urls["latest"], cfg) as r:
            data = json.loads(r.read().decode("utf-8"))
        if urls["kind"] == "github":
            sha = data["sha"]
            date = data.get("commit", {}).get("committer", {}).get("date")
            msg = data.get("commit", {}).get("message", "")
        else:
            sha = data["commit"]["id"]
            date = data["commit"].get("timestamp")
            msg = data["commit"].get("message", "")
        msg = (msg or "").strip().splitlines()[0] if msg else ""
        _set(remote_sha=sha, remote_date=date)
        local = local_version()
        if local and local == sha:
            _set(state="uptodate", message="You have the latest version.")
            _log(f"Up to date ({sha[:8]}).")
        else:
            what = f"Update available: {msg}" if msg else "Update available."
            _set(state="available", message=what)
            _log(f"Latest is {sha[:8]}; installed is {local[:8] if local else 'unknown'}.")
    except Exception as exc:  # noqa: BLE001
        _set(state="error", message=f"Could not reach the update server: {exc}")
        _log(f"Check failed: {exc}")
    return get_status()


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def start_update() -> None:
    """Kick off the update in a background thread. Poll get_status()."""
    st = get_status()
    if st["state"] in ("updating", "restarting"):
        return
    threading.Thread(target=_run_update, name="mcm-updater", daemon=True).start()


def _ignore_protected(_dir, names):
    return {n for n in names if n in PROTECTED_DIRS or n.startswith(PROTECTED_PREFIX)}


def _find_source(extract_dir: Path) -> Path | None:
    for p in extract_dir.rglob("main.py"):
        if p.parent.name == "app":
            return p.parent.parent
    return None


def _run_update() -> None:
    cfg = load_config()
    urls = _urls(cfg)
    _set(state="updating", message="Downloading the latest version...")
    tmp = Path(tempfile.mkdtemp(prefix="mcm_update_"))
    try:
        # 1. Download
        zpath = tmp / "update.zip"
        _log(f"Downloading {urls['archive']}")
        with _open(urls["archive"], cfg, timeout=600) as r, open(zpath, "wb") as fh:
            shutil.copyfileobj(r, fh)
        _log(f"Downloaded {zpath.stat().st_size / 1e6:.1f} MB")

        # 2. Extract
        _set(message="Unpacking...")
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(tmp / "x")
        src = _find_source(tmp / "x")
        if src is None:
            raise RuntimeError("Archive does not contain app/main.py")
        _log(f"New files at {src}")

        # 3. Back up current app/ (same as Update.bat)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
        backup = ROOT / f"{PROTECTED_PREFIX}{stamp}"
        _set(message="Backing up current version...")
        shutil.copytree(ROOT / "app", backup / "app", ignore=_ignore_protected)
        for f in ("Setup.bat", "Update.bat", "Start App.bat", "requirements.txt"):
            if (ROOT / f).is_file():
                shutil.copy2(ROOT / f, backup / f)
        _log(f"Backup saved to {backup.name}\\")

        old_req = (ROOT / "requirements.txt").read_text(encoding="utf-8") if (ROOT / "requirements.txt").is_file() else ""

        # 4. Copy new files in. Never deletes anything in the install.
        _set(message="Installing new files...")
        n = 0
        for item in src.iterdir():
            if item.name in PROTECTED_DIRS or item.name.startswith(PROTECTED_PREFIX):
                continue
            dest = ROOT / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True, ignore=_ignore_protected)
            else:
                shutil.copy2(item, dest)
            n += 1
        _log(f"Copied {n} top-level items into {ROOT}")

        # 5. Packages, only if requirements.txt changed
        new_req = (ROOT / "requirements.txt").read_text(encoding="utf-8") if (ROOT / "requirements.txt").is_file() else ""
        if new_req and new_req != old_req:
            _set(message="Package list changed - installing Python packages (this can take a few minutes)...")
            _log("requirements.txt changed; running pip install")
            _pip_install()
        else:
            _log("requirements.txt unchanged; skipping pip")

        # 6. Record version
        sha = get_status().get("remote_sha")
        if sha:
            VERSION_FILE.write_text(sha, encoding="utf-8")
            _log(f"Installed version {sha[:8]}")

        # 7. Relaunch
        _set(state="restarting", message="Update installed. Restarting the app...")
        _log("Restarting server")
        _relaunch()
    except Exception as exc:  # noqa: BLE001
        _set(state="error", message=f"Update failed: {exc}")
        _log(f"FAILED: {exc}")
        _log("Your previous files are still in place (see the _backup_ folder).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pip_install() -> None:
    py = sys.executable
    site = ROOT / "python-3.13" / "Lib" / "site-packages"
    cmd = [py, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "--no-warn-script-location"]
    if site.is_dir():
        cmd += ["--target", str(site), "--upgrade"]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
        for line in tail:
            _log(f"pip: {line}")
        if proc.returncode != 0:
            _log("WARNING: pip reported errors; the app may still run.")
    except Exception as exc:  # noqa: BLE001
        _log(f"WARNING: pip install failed: {exc}")


def _relaunch() -> None:
    """Spawn a detached helper that waits for this process to exit, then
    starts a fresh server. Then exit this process."""
    py = sys.executable
    main = str(_APP / "main.py")
    env = dict(os.environ, MCM_NO_BROWSER="1")   # the open tab reloads itself
    helper = (
        "import subprocess,sys,time,os;"
        "time.sleep(3);"
        f"subprocess.Popen([{py!r},{main!r}],cwd={str(ROOT)!r},"
        "creationflags=(getattr(subprocess,'CREATE_NEW_CONSOLE',0)))"
    )
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([py, "-c", helper], cwd=str(ROOT), env=env,
                         creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([py, "-c", helper], cwd=str(ROOT), env=env,
                         start_new_session=True, close_fds=True)
    # Give the HTTP response that reported "restarting" time to reach the browser.
    threading.Timer(1.5, lambda: os._exit(0)).start()
