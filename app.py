#!/usr/bin/env python3
"""
godown — gofile.io ダウンローダー Webアプリ

ローカルでも、Render等の無料Webサービスにデプロイしても動く。
処理(トークン計算・コンテンツ取得・ダウンロード・ZIP化)はすべてサーバー側で行い、
できあがったZIPはブラウザから直接ダウンロードできる(サーバー上にパスを固定保存しない)。
進捗ログは日本語/英語(lang="ja"/"en")に対応している。

流れ:
    1. POST /api/list        URLからファイル一覧(名前・サイズ・サムネの有無)だけ取得
    2. GET  /api/thumbnail/.. 一覧のサムネイル画像をサーバー経由で中継表示
    3. POST /api/start        選んだファイルだけダウンロード→ZIP化
    4. GET  /download/..      できたZIPをブラウザにダウンロードさせる

ローカル実行:
    pip install -r requirements.txt
    python app.py
    ブラウザで http://127.0.0.1:5000 を開く
"""
from __future__ import annotations  # Python 3.9でも動くようにするため

import hashlib
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request, send_file

app = Flask(__name__)

API_BASE = "https://api.gofile.io"
USER_AGENT = "Mozilla/5.0"
WT_SALT = "12af056dacea0b"  # gofile公式Webクライアントが使っている固定ソルト

# 完成したZIPを一時的に置いておく場所(ダウンロードされたら消える)
JOB_STORAGE_DIR = Path(tempfile.gettempdir()) / "gofile_intake_jobs"
JOB_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# 何らかの理由で回収されなかった古いZIP/一覧情報を掃除するまでの時間
MAX_AGE_SECONDS = 2 * 60 * 60  # 2時間

JOBS: dict = {}
JOBS_LOCK = threading.Lock()

# URLから取得したファイル一覧(選択待ち)。listing_idごとにセッションとファイル情報を保持する。
LISTINGS: dict = {}
LISTINGS_LOCK = threading.Lock()

DEFAULT_LANG = "ja"
SUPPORTED_LANGS = ("ja", "en")

MESSAGES = {
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
    "no_files_found": {"ja": "ファイルが見つかりませんでした", "en": "No files were found"},
    "listing_expired": {
        "ja": "一覧の有効期限が切れました。もう一度URLを入力してください。",
        "en": "This file list has expired. Please enter the URL again.",
    },
    "no_selection": {"ja": "ファイルを1つ以上選んでください", "en": "Select at least one file"},
}


def resolve_lang(value) -> str:
    return value if value in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str, *fmt_args) -> str:
    template = MESSAGES[key].get(lang, MESSAGES[key][DEFAULT_LANG])
    return template.format(*fmt_args) if fmt_args else template


class PasswordRequiredError(RuntimeError):
    """パスワードが必要、または間違っている場合に送出する。"""


def sanitize_zip_name(name: str | None, fallback: str) -> str:
    """ユーザーが指定したZIP名を安全なファイル名に整える。空や不正な場合はfallbackを使う。"""
    name = (name or "").strip()
    if name.lower().endswith(".zip"):
        name = name[:-4]
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().rstrip(". ")
    name = name[:150]
    return name or fallback


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


def _append_file(node: dict, rel_dir: str, files: list):
    files.append(
        {
            "id": node["id"],
            "name": node["name"],
            "size": node.get("size", 0),
            "mimetype": node.get("mimetype", ""),
            "thumbnail": node.get("thumbnail"),
            "link": node["link"],
            "rel_dir": rel_dir,
        }
    )


def _collect_files(session, node, account_token, password_hash, rel_dir, files):
    for child_id, child in node.get("children", {}).items():
        if child.get("type") == "folder":
            child_full = get_content(session, child_id, account_token, password_hash)
            sub_rel = os.path.join(rel_dir, child.get("name", child_id))
            _collect_files(session, child_full, account_token, password_hash, sub_rel, files)
        else:
            _append_file(child, rel_dir, files)


def build_file_list(session, content, account_token, password_hash):
    """gofileのコンテンツツリーを再帰的にたどり、ファイルだけをフラットな一覧にする。
    フォルダ構造は各ファイルの rel_dir(相対フォルダパス)として保持する。"""
    root_name = content.get("name", content.get("id"))
    files: list = []
    if content.get("type") == "folder":
        for child_id, child in content.get("children", {}).items():
            if child.get("type") == "folder":
                child_full = get_content(session, child_id, account_token, password_hash)
                sub_rel = child.get("name", child_id)
                _collect_files(session, child_full, account_token, password_hash, sub_rel, files)
            else:
                _append_file(child, "", files)
    else:
        _append_file(content, "", files)
    return root_name, files


# ---------------- job runner (選択されたファイルのダウンロード) ----------------

def run_job(job_id: str, session: requests.Session, files: list, root_name: str, zip_name: str, lang: str):
    def log(msg: str):
        with JOBS_LOCK:
            JOBS[job_id]["log"].append(msg)

    try:
        with tempfile.TemporaryDirectory() as tmp_root:
            target_dir = os.path.join(tmp_root, root_name)
            os.makedirs(target_dir, exist_ok=True)

            for f in files:
                dest_dir = os.path.join(target_dir, f["rel_dir"]) if f["rel_dir"] else target_dir
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, f["name"])
                log(t("downloading", lang, f["name"]))
                download_file(session, f["link"], dest)

            log(t("zipping", lang))
            # 内部的な保存名はjob_idにして衝突を避け、ダウンロード時のファイル名はzip_nameにする
            zip_base = str(JOB_STORAGE_DIR / job_id)
            zip_path = shutil.make_archive(zip_base, "zip", target_dir)

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["zip_path"] = zip_path
            JOBS[job_id]["download_name"] = f"{zip_name}.zip"
            JOBS[job_id]["created_at"] = time.time()
        log(t("done", lang))

    except Exception as e:  # noqa: BLE001
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
        log(f"{t('error_prefix', lang)} {e}")


def cleanup_old_entries():
    """一定時間放置されたZIP/ファイル一覧を掃除する(ディスク・メモリ圧迫防止)。"""
    while True:
        time.sleep(600)
        cutoff = time.time() - MAX_AGE_SECONDS

        with JOBS_LOCK:
            expired_jobs = [jid for jid, j in JOBS.items() if j.get("created_at", 0) and j["created_at"] < cutoff]
            for jid in expired_jobs:
                zip_path = JOBS[jid].get("zip_path")
                if zip_path and os.path.isfile(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
                del JOBS[jid]

        with LISTINGS_LOCK:
            expired_listings = [lid for lid, l in LISTINGS.items() if l["created_at"] < cutoff]
            for lid in expired_listings:
                del LISTINGS[lid]


threading.Thread(target=cleanup_old_entries, daemon=True).start()


# ---------------- routes ----------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ping")
def ping():
    """UptimeRobotやcron-job.orgなど外形監視からの定期pingを受けて、
    Renderの無料プランがスリープしないようにするための軽いエンドポイント。"""
    return "ok", 200


@app.route("/api/list", methods=["POST"])
def list_contents():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    password = data.get("password") or None
    lang = resolve_lang(data.get("lang"))

    if not url:
        return jsonify({"error": t("url_missing", lang)}), 400

    try:
        content_id = extract_content_id(url)
        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None

        session = make_session()
        account_token = get_guest_token(session)
        content = get_content(session, content_id, account_token, password_hash)
        root_name, files = build_file_list(session, content, account_token, password_hash)
    except PasswordRequiredError:
        return jsonify({"error": t("password_required", lang)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"{t('error_prefix', lang)} {e}"}), 400

    if not files:
        return jsonify({"error": t("no_files_found", lang)}), 400

    listing_id = uuid.uuid4().hex
    with LISTINGS_LOCK:
        LISTINGS[listing_id] = {
            "session": session,
            "root_name": root_name,
            "content_id": content_id,
            "files": {f["id"]: f for f in files},
            "created_at": time.time(),
        }

    return jsonify(
        {
            "listing_id": listing_id,
            "root_name": root_name,
            "content_id": content_id,
            "files": [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "size": f["size"],
                    "mimetype": f["mimetype"],
                    "has_thumbnail": bool(f.get("thumbnail")),
                    "rel_dir": f["rel_dir"],
                }
                for f in files
            ],
        }
    )


@app.route("/api/thumbnail/<listing_id>/<file_id>")
def thumbnail(listing_id, file_id):
    listing = LISTINGS.get(listing_id)
    if not listing:
        return "", 404
    file_info = listing["files"].get(file_id)
    if not file_info or not file_info.get("thumbnail"):
        return "", 404
    try:
        r = listing["session"].get(file_info["thumbnail"], timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return "", 404
    return Response(r.content, mimetype=r.headers.get("Content-Type", "image/jpeg"))


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True) or {}
    listing_id = data.get("listing_id")
    selected_ids = data.get("selected_ids") or []
    lang = resolve_lang(data.get("lang"))

    listing = LISTINGS.get(listing_id)
    if not listing:
        return jsonify({"error": t("listing_expired", lang)}), 400

    selected_files = [listing["files"][fid] for fid in selected_ids if fid in listing["files"]]
    if not selected_files:
        return jsonify({"error": t("no_selection", lang)}), 400

    zip_name = sanitize_zip_name(data.get("zip_name"), listing["content_id"])

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "log": [], "zip_path": None, "download_name": None}

    thread = threading.Thread(
        target=run_job,
        args=(job_id, listing["session"], selected_files, listing["root_name"], zip_name, lang),
        daemon=True,
    )
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