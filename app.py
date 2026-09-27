#!/usr/bin/env python3
"""
godown — gofile.io ダウンローダー Webアプリ

ローカルでも、Render等の無料Webサービスにデプロイしても動く。
処理(トークン計算・コンテンツ取得・ダウンロード・ZIP化)はすべてサーバー側で行い、
できあがったZIPはブラウザから直接ダウンロードできる(サーバー上にパスを固定保存しない)。
進捗ログは日本語/英語(lang="ja"/"en")に対応している。

ローカル実行:
    pip install -r requirements.txt
    python app.py
    ブラウザで http://127.0.0.1:5000 を開く
"""
from __future__ import annotations  # Python 3.9でも動くようにするため

import hashlib
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)

API_BASE = "https://api.gofile.io"
USER_AGENT = "Mozilla/5.0"
WT_SALT = "12af056dacea0b"  # gofile公式Webクライアントが使っている固定ソルト

# 完成したZIPを一時的に置いておく場所(ダウンロードされたら消える)
JOB_STORAGE_DIR = Path(tempfile.gettempdir()) / "gofile_intake_jobs"
JOB_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# 何らかの理由で回収されなかった古いZIPを掃除するまでの時間
MAX_JOB_AGE_SECONDS = 2 * 60 * 60  # 2時間

JOBS: dict = {}
JOBS_LOCK = threading.Lock()

DEFAULT_LANG = "ja"
SUPPORTED_LANGS = ("ja", "en")

MESSAGES = {
    "content_id": {"ja": "コンテンツID: {}", "en": "Content ID: {}"},
    "creating_account": {"ja": "ゲストアカウントを作成中...", "en": "Creating guest account..."},
    "fetching_content": {"ja": "コンテンツ情報を取得中...", "en": "Fetching content info..."},
    "downloading": {"ja": "ダウンロード中: {}", "en": "Downloading: {}"},
    "zipping": {"ja": "ZIPを作成中...", "en": "Creating ZIP..."},
    "done": {"ja": "完了。ダウンロードできます。", "en": "Done. Ready to download."},
    "error_prefix": {"ja": "エラー:", "en": "Error:"},
    "password_required": {
        "ja": "パスワードが必要、または間違っています。",
        "en": "Password required or incorrect.",
    },
    "url_missing": {"ja": "URLが指定されていません", "en": "No URL was provided"},
    "file_not_found": {"ja": "ファイルが見つかりません", "en": "File not found"},
}


def resolve_lang(value) -> str:
    return value if value in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str, *fmt_args) -> str:
    template = MESSAGES[key].get(lang, MESSAGES[key][DEFAULT_LANG])
    return template.format(*fmt_args) if fmt_args else template


class PasswordRequiredError(RuntimeError):
    """パスワードが必要、または間違っている場合に送出する。"""


# ---------------- gofile API helper ----------------

def extract_content_id(url_or_id: str) -> str:
    if "gofile.io/d/" in url_or_id:
        return url_or_id.split("gofile.io/d/")[-1].split("?")[0].split("/")[0]
    return url_or_id.rstrip("/").split("/")[-1]


def generate_website_token(user_agent: str, account_token: str) -> str:
    """gofile公式Webクライアントと同じ方法でX-Website-Tokenを計算する。"""
    time_slot = int(time.time()) // 14400
    raw = f"{user_agent}::en-US::{account_token}::{time_slot}::{WT_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Accept-Encoding": "gzip",
            "User-Agent": USER_AGENT,
            "Connection": "keep-alive",
            "Accept": "*/*",
            "Origin": "https://gofile.io",
            "Referer": "https://gofile.io/",
        }
    )
    return s


def get_guest_token(session: requests.Session) -> str:
    wt = generate_website_token(USER_AGENT, "")
    r = session.post(
        f"{API_BASE}/accounts", headers={"X-Website-Token": wt, "X-BL": "en-US"}, timeout=15
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Failed to create guest account: {data}")
    token = data["data"]["token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    return token


def get_content(session, content_id, account_token, password_hash=None):
    wt = generate_website_token(USER_AGENT, account_token)
    url = f"{API_BASE}/contents/{content_id}?cache=true&sortField=createTime&sortDirection=1"
    if password_hash:
        url += f"&password={password_hash}"
    r = session.get(url, headers={"X-Website-Token": wt, "X-BL": "en-US"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Failed to fetch content: {data}")
    content = data["data"]
    if "passwordStatus" in content and content["passwordStatus"] != "passwordOk":
        raise PasswordRequiredError()
    return content


def download_file(session: requests.Session, url: str, dest_path: str):
    with session.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)


def walk_and_download(session, node, account_token, password_hash, base_dir, log, lang):
    if node.get("type") == "file":
        dest = os.path.join(base_dir, node["name"])
        log(t("downloading", lang, node["name"]))
        download_file(session, node["link"], dest)
        return

    folder_dir = os.path.join(base_dir, node.get("name", node.get("id", "folder")))
    os.makedirs(folder_dir, exist_ok=True)
    for child_id, child in node.get("children", {}).items():
        if child.get("type") == "folder":
            child_full = get_content(session, child_id, account_token, password_hash)
            walk_and_download(session, child_full, account_token, password_hash, folder_dir, log, lang)
        else:
            walk_and_download(session, child, account_token, password_hash, folder_dir, log, lang)


# ---------------- job runner ----------------

def run_job(job_id: str, url: str, password: str | None, lang: str):
    def log(msg: str):
        with JOBS_LOCK:
            JOBS[job_id]["log"].append(msg)

    try:
        content_id = extract_content_id(url)
        log(t("content_id", lang, content_id))

        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None

        session = make_session()
        log(t("creating_account", lang))
        account_token = get_guest_token(session)

        log(t("fetching_content", lang))
        content = get_content(session, content_id, account_token, password_hash)
        root_name = content.get("name", content_id)

        with tempfile.TemporaryDirectory() as tmp_root:
            if content.get("type") == "folder":
                target_dir = os.path.join(tmp_root, root_name)
                os.makedirs(target_dir, exist_ok=True)
                for child_id, child in content.get("children", {}).items():
                    if child.get("type") == "folder":
                        child_full = get_content(session, child_id, account_token, password_hash)
                        walk_and_download(session, child_full, account_token, password_hash, target_dir, log, lang)
                    else:
                        walk_and_download(session, child, account_token, password_hash, target_dir, log, lang)
            else:
                target_dir = tmp_root
                walk_and_download(session, content, account_token, password_hash, target_dir, log, lang)

            log(t("zipping", lang))
            # 内部的な保存名はjob_idにして衝突を避け、ダウンロード時の名前だけroot_nameにする
            zip_base = str(JOB_STORAGE_DIR / job_id)
            zip_path = shutil.make_archive(zip_base, "zip", target_dir)

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["zip_path"] = zip_path
            JOBS[job_id]["download_name"] = f"{root_name}.zip"
            JOBS[job_id]["created_at"] = time.time()
        log(t("done", lang))

    except PasswordRequiredError:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
        log(t("password_required", lang))

    except Exception as e:  # noqa: BLE001
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
        log(f"{t('error_prefix', lang)} {e}")


def cleanup_old_jobs():
    """一定時間ダウンロードされなかったZIPを掃除する(ディスク圧迫防止)。"""
    while True:
        time.sleep(600)
        cutoff = time.time() - MAX_JOB_AGE_SECONDS
        with JOBS_LOCK:
            expired = [jid for jid, j in JOBS.items() if j.get("created_at", 0) and j["created_at"] < cutoff]
            for jid in expired:
                zip_path = JOBS[jid].get("zip_path")
                if zip_path and os.path.isfile(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
                del JOBS[jid]


threading.Thread(target=cleanup_old_jobs, daemon=True).start()


# ---------------- routes ----------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ping")
def ping():
    """UptimeRobotやcron-job.orgなど外形監視からの定期pingを受けて、
    Renderの無料プランがスリープしないようにするための軽いエンドポイント。"""
    return "ok", 200


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    password = data.get("password") or None
    lang = resolve_lang(data.get("lang"))

    if not url:
        return jsonify({"error": t("url_missing", lang)}), 400

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "log": [], "zip_path": None, "download_name": None}

    thread = threading.Thread(target=run_job, args=(job_id, url, password, lang), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    # zip_pathは内部の実パスなのでクライアントには返さない
    return jsonify({"status": job["status"], "log": job["log"], "ready": job["status"] == "done"})


@app.route("/download/<job_id>")
def download(job_id):
    lang = resolve_lang(request.args.get("lang"))
    job = JOBS.get(job_id)
    if not job or job["status"] != "done" or not job.get("zip_path"):
        return jsonify({"error": t("file_not_found", lang)}), 404
    return send_file(job["zip_path"], as_attachment=True, download_name=job["download_name"])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
