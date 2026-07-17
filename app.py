"""
MAPHRONIX Web - Final (Phases 1-4)
====================================
Upload videos -> extract GPS -> view route + play video synced to the map ->
HD screenshots + coordinate search -> login gate + email notifications.

All secrets are read from environment variables (see .env.example) -- never
hardcoded, unlike the original desktop app.
"""

import os
import socket
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime
from functools import wraps
from email.message import EmailMessage
import smtplib

from flask import (
    Flask, render_template, request, jsonify, send_from_directory,
    session, redirect, url_for, Request as FlaskRequest,
)
from werkzeug.utils import secure_filename

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    import requests
except ImportError:
    requests = None

# ---------------------------------------------------------------------------
# Configuration -- all secrets come from environment variables. Copy
# .env.example to .env and fill in real values; python-dotenv loads it below.
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv()

def env(name, default=None):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def required_env(name):
    value = env(name)
    if value is None:
        raise RuntimeError(f"{name} is not set. Add it to your .env file.")
    return value


def required_env_int(name):
    return int(required_env(name))


APP_TIMEZONE = required_env("APP_TIMEZONE")
APP_TZ = ZoneInfo(APP_TIMEZONE) if ZoneInfo else None
EXIFTOOL_PATH = required_env("EXIFTOOL_PATH")
EXIFTOOL_TIMEOUT_SECONDS = required_env_int("EXIFTOOL_TIMEOUT_SECONDS")
FLASK_SECRET_KEY = env("FLASK_SECRET_KEY")
APP_LOGIN_PASSWORD = env("APP_LOGIN_PASSWORD")
APP_HOST = required_env("APP_HOST")
APP_PORT = required_env_int("APP_PORT")
APP_DEBUG = required_env("APP_DEBUG").lower() in {"1", "true", "yes", "on"}
EMAIL_SENDER = env("EMAIL_SENDER")
EMAIL_PASSWORD = env("EMAIL_PASSWORD")
EMAIL_RECEIVER = env("EMAIL_RECEIVER")
SMTP_HOST = required_env("SMTP_HOST")
SMTP_PORT = required_env_int("SMTP_PORT")
IP_LOOKUP_URL = required_env("IP_LOOKUP_URL")
IP_LOOKUP_TIMEOUT_SECONDS = required_env_int("IP_LOOKUP_TIMEOUT_SECONDS")
EMAIL_NOTIFICATIONS_ENABLED = bool(EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECEIVER)
LEAFLET_CSS_URL = required_env("LEAFLET_CSS_URL")
LEAFLET_JS_URL = required_env("LEAFLET_JS_URL")
MAP_TILE_URL = required_env("MAP_TILE_URL")
MAP_TILE_SUBDOMAINS = [s.strip() for s in required_env("MAP_TILE_SUBDOMAINS").split(",") if s.strip()]
MAP_TILE_MAX_ZOOM = required_env_int("MAP_TILE_MAX_ZOOM")
SCREENSHOT_WIDTH = required_env_int("SCREENSHOT_WIDTH")
SCREENSHOT_HEIGHT = required_env_int("SCREENSHOT_HEIGHT")

if not FLASK_SECRET_KEY:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. Add it to your .env file "
        "(any long random string works, e.g. generate one with: "
        "python -c \"import secrets; print(secrets.token_hex(32))\")"
    )
if not APP_LOGIN_PASSWORD:
    raise RuntimeError("APP_LOGIN_PASSWORD is not set. Add it to your .env file.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.abspath(required_env("UPLOAD_FOLDER"))
ALLOWED_EXTENSIONS = {
    ext.strip() if ext.strip().startswith(".") else f".{ext.strip()}"
    for ext in required_env("ALLOWED_EXTENSIONS").lower().split(",")
    if ext.strip()
}
LOG_FILE_PATH = os.path.abspath(required_env("LOG_FILE_PATH"))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def parse_size_to_bytes(value):
    """Parse size values with suffixes such as GB, MB, KB, or raw bytes."""
    if not value:
        raise ValueError("Size value is required")
    text = str(value).strip().upper().replace(" ", "")
    units = (
        ("GB", 1024 ** 3),
        ("G", 1024 ** 3),
        ("MB", 1024 ** 2),
        ("M", 1024 ** 2),
        ("KB", 1024),
        ("K", 1024),
        ("B", 1),
    )
    for suffix, multiplier in units:
        if text.endswith(suffix):
            return int(float(text[:-len(suffix)]) * multiplier)
    return int(float(text))


MAX_UPLOAD_SIZE = required_env("MAX_UPLOAD_SIZE")
MAX_CONTENT_LENGTH = parse_size_to_bytes(MAX_UPLOAD_SIZE)


class LargeUploadRequest(FlaskRequest):
    """Store multipart file streams on the upload disk instead of OS temp."""

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return tempfile.NamedTemporaryFile(
            "wb+", dir=UPLOAD_FOLDER, prefix="incoming_", suffix=".tmp", delete=False
        )


def _uploaded_temp_path(file_storage):
    stream_name = getattr(file_storage.stream, "name", None)
    if not isinstance(stream_name, str):
        return None
    temp_path = os.path.abspath(stream_name)
    upload_dir = os.path.abspath(UPLOAD_FOLDER)
    if os.path.dirname(temp_path) != upload_dir:
        return None
    return temp_path


def save_uploaded_file(file_storage, destination):
    temp_path = _uploaded_temp_path(file_storage)
    if temp_path and os.path.exists(temp_path):
        file_storage.stream.flush()
        file_storage.stream.close()
        os.replace(temp_path, destination)
        return
    file_storage.save(destination)


def discard_uploaded_temp(file_storage):
    temp_path = _uploaded_temp_path(file_storage)
    try:
        file_storage.close()
    except Exception:
        pass
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass


app = Flask(__name__)
app.request_class = LargeUploadRequest
app.secret_key = FLASK_SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


# ---------------------------------------------------------------------------
# Activity logging + email notifications (ported from log_action /
# send_login_email / send_activity_log_email)
# ---------------------------------------------------------------------------
def log_action(text):
    ts = datetime.now(APP_TZ).strftime("%d-%b-%Y %H:%M:%S") if APP_TZ else datetime.now().isoformat()
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {text}\n")
    except Exception:
        pass


def _send_email(subject, body, attachment_path=None):
    if not EMAIL_NOTIFICATIONS_ENABLED:
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg.set_content(body)
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                msg.add_attachment(f.read(), maintype="text", subtype="plain",
                                    filename=os.path.basename(attachment_path))
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
    except Exception:
        pass  # best-effort, same as the original desktop app


def send_login_email_async(username):
    def _run():
        hostname = socket.gethostname()
        ip_data = {}
        if requests:
            try:
                ip_data = requests.get(IP_LOOKUP_URL, timeout=IP_LOOKUP_TIMEOUT_SECONDS).json()
            except Exception:
                pass
        if os.path.exists(LOG_FILE_PATH):
            os.remove(LOG_FILE_PATH)
        log_action(f"User logged in: {username}")
        login_time = datetime.now(APP_TZ).strftime("%d-%b-%Y %H:%M:%S") if APP_TZ else datetime.now().isoformat()
        body = (
            f"User : {username}\nLogin Time : {login_time}\n\n"
            f"System : {hostname}\n"
            f"IP : {ip_data.get('query', 'N/A')}\n"
            f"City : {ip_data.get('city', 'N/A')}\n"
            f"Region : {ip_data.get('regionName', 'N/A')}\n"
            f"Country : {ip_data.get('country', 'N/A')}\n"
            f"ISP : {ip_data.get('isp', 'N/A')}"
        )
        _send_email(f"MAPHRONIX Web - Login Alert: {username}", body)
    threading.Thread(target=_run, daemon=True).start()


def send_activity_log_email_async():
    def _run():
        if not os.path.exists(LOG_FILE_PATH):
            return
        log_action("Session ended")
        _send_email("MAPHRONIX Web - Activity Log", "Attached is the activity log.", LOG_FILE_PATH)
        if os.path.exists(LOG_FILE_PATH):
            os.remove(LOG_FILE_PATH)
    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Login gate
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith(("/upload", "/video")):
                return jsonify({"error": "Not logged in"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if username and password == APP_LOGIN_PASSWORD:
            session["user"] = username
            send_login_email_async(username)
            log_action(f"Btn: Login ({username})")
            return redirect(url_for("home"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html", error=None)


@app.route("/logout", methods=["POST"])
def logout():
    username = session.get("user")
    if username:
        log_action(f"Btn: Logout ({username})")
        send_activity_log_email_async()
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Core logic (ported from GPXThread / load_folder)
# ---------------------------------------------------------------------------
def is_allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


def extract_gps_points(video_path):
    cmd = [EXIFTOOL_PATH, "-ee", "-n", "-p", "$GPSLatitude,$GPSLongitude", video_path]
    try:
        process = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=EXIFTOOL_TIMEOUT_SECONDS,
        )
        pts = []
        for line in process.stdout.strip().split("\n"):
            if "," not in line:
                continue
            lat_str, lon_str = line.split(",")[:2]
            pts.append({"lat": float(lat_str), "lon": float(lon_str)})
        return pts
    except FileNotFoundError:
        raise RuntimeError(
            f"exiftool was not found at '{EXIFTOOL_PATH}'. "
            "Install it and/or set EXIFTOOL_PATH in your .env file."
        )
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def home():
    frontend_config = {
        "leafletCssUrl": LEAFLET_CSS_URL,
        "leafletJsUrl": LEAFLET_JS_URL,
        "mapTileUrl": MAP_TILE_URL,
        "mapTileSubdomains": MAP_TILE_SUBDOMAINS,
        "mapTileMaxZoom": MAP_TILE_MAX_ZOOM,
        "screenshotWidth": SCREENSHOT_WIDTH,
        "screenshotHeight": SCREENSHOT_HEIGHT,
    }
    return render_template(
        "index.html",
        username=session.get("user"),
        frontend_config=frontend_config,
    )


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("videos")
    if not files:
        return jsonify({"error": "No files received"}), 400

    results = []
    for f in files:
        if not f or not f.filename:
            if f:
                discard_uploaded_temp(f)
            continue
        if not is_allowed_file(f.filename):
            results.append({
                "filename": f.filename,
                "error": "Unsupported file type (only .mp4 / .mov allowed)",
            })
            discard_uploaded_temp(f)
            continue

        # Prefix with a short unique id so same-named files from different
        # folders never collide on disk or in the browser's GPS cache.
        safe_name = secure_filename(f.filename) or "video"
        stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
        save_uploaded_file(f, save_path)
        log_action(f"Uploaded: {f.filename}")

        try:
            points = extract_gps_points(save_path)
            results.append({
                "id": stored_name,
                "filename": f.filename,
                "points": points,
                "point_count": len(points),
            })
        except RuntimeError as e:
            results.append({"id": stored_name, "filename": f.filename, "error": str(e)})

    return jsonify({"results": results})


@app.route("/video/<path:stored_name>")
@login_required
def video(stored_name):
    """Streams an uploaded video by its unique stored name (see /upload)."""
    return send_from_directory(app.config["UPLOAD_FOLDER"], secure_filename(stored_name))


@app.errorhandler(413)
def too_large(_e):
    return jsonify({
        "error": f"File too large. Max upload size is {MAX_UPLOAD_SIZE} per request."
    }), 413


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=APP_DEBUG)
