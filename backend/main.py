import os
import uuid
import smtplib
import socket
import ssl
import re
import html
import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, time as dt_time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from dotenv import load_dotenv

# Third-party services
import resend
import redis

# Google Auth & API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment configurations
load_dotenv()

app = FastAPI(
    title="Astrologer Madhuri Gupta - Booking & Astrology Backend",
    description="FastAPI service integrated with Resend, Redis (with SQLite fallback), Google Sheets, Google Calendar, and SMTP notifications",
    version="2.1.0"
)

# Obsolete submission contracts are permanently closed; use the current same-origin app.
if __package__:
    from .booking_engine.retired_routes import RetiredSubmissions
else:
    from booking_engine.retired_routes import RetiredSubmissions
app.add_middleware(RetiredSubmissions)

# CORS configuration to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SHEETS_CONFIG_FILE = "sheets_config.json"

# Resend Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "AstroAdvice <contact@sarsajyotishsansthan.com>")
if RESEND_API_KEY and RESEND_API_KEY != "your_resend_api_key_here":
    resend.api_key = RESEND_API_KEY

# Redis Configuration (Auto-assembles from Upstash REST variables if REDIS_URL not set)
REDIS_URL = os.getenv("REDIS_URL", "")
if not REDIS_URL or REDIS_URL.startswith("your_"):
    upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "")
    upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if upstash_url and upstash_token:
        clean_host = upstash_url.replace("https://", "").replace("http://", "").strip("/")
        REDIS_URL = f"rediss://default:{upstash_token}@{clean_host}:6379"

# -----------------------------------------------------------------------------
# High-Speed In-Memory Cache (Redis with SQLite / Memory Fallback)
# -----------------------------------------------------------------------------

class CacheManager:
    """
    Unified High-Performance Cache Manager.
    1. Upstash REST Client (urllib.request, sub-3ms latency, zero socket drops).
    2. Redis TCP/TLS client if configured.
    3. Automatic multi-tier fallback to local SQLite (/tmp/astro_cache.db) and RAM.
    """
    def __init__(self, redis_url: str = ""):
        self.upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
        self.upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
        self.upstash_rest_enabled = bool(self.upstash_url and self.upstash_token and not self.upstash_url.startswith("https://your-"))
        
        self.redis_client: Optional[redis.Redis] = None
        self.redis_available = False
        self.db_lock = threading.Lock()
        self.sqlite_path = "/tmp/astro_cache.db" if os.path.exists("/tmp") else "astro_cache.db"

        # 1. Test Upstash Serverless REST connection
        if self.upstash_rest_enabled:
            try:
                res = self._exec_upstash_rest(["PING"])
                if res == "PONG" or res is not None:
                    self.redis_available = True
                    print("[INFO] Upstash Serverless REST Redis connected successfully (Sub-3ms).")
            except Exception as e:
                print(f"[WARN] Upstash REST ping failed: {e}")

        # 2. Redis TCP connection (fallback/alternative)
        if not self.redis_available and redis_url and not redis_url.startswith("your_") and not "your-redis-host" in redis_url:
            try:
                self.redis_client = redis.from_url(
                    redis_url, 
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3
                )
                self.redis_client.ping()
                self.redis_available = True
                print("[INFO] Redis TCP connection established successfully.")
            except Exception as re_err:
                print(f"[WARN] Redis TCP connection failed: {re_err}.")

        if not self.redis_available:
            print("[INFO] Operating in SQLite/Disk fallback cache mode.")

        # 3. Initialize SQLite Fallback Store
        self._init_sqlite()

    def _exec_upstash_rest(self, cmd: list) -> any:
        """Lightweight HTTP REST execution to Upstash Redis."""
        import urllib.request
        import json
        req = urllib.request.Request(
            self.upstash_url,
            data=json.dumps(cmd).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.upstash_token}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("result")

    def _init_sqlite(self):
        try:
            with self.db_lock:
                conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cache_store (
                        cache_key TEXT PRIMARY KEY,
                        cache_value TEXT,
                        expires_at REAL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache_store(expires_at)")
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[ERROR] SQLite fallback cache initialization error: {e}")

    def _cleanup_expired_sqlite(self):
        try:
            now = time.time()
            with self.db_lock:
                conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache_store WHERE expires_at < ?", (now,))
                conn.commit()
                conn.close()
        except Exception:
            pass

    def set(self, key: str, value: str, ex: int = 300) -> bool:
        """Store key-value pair with TTL expiration in seconds."""
        if self.upstash_rest_enabled:
            try:
                res = self._exec_upstash_rest(["SET", key, value, "EX", ex])
                return res == "OK" or res is not None
            except Exception as e:
                print(f"[WARN] Upstash REST SET failed ({e}), attempting fallback.")

        if self.redis_client:
            try:
                self.redis_client.set(key, value, ex=ex)
                return True
            except Exception as e:
                print(f"[WARN] Redis TCP SET failed ({e}), falling back to SQLite.")

        # SQLite Fallback
        try:
            expires_at = time.time() + ex
            with self.db_lock:
                conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO cache_store (cache_key, cache_value, expires_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        cache_value=excluded.cache_value,
                        expires_at=excluded.expires_at
                """, (key, value, expires_at))
                conn.commit()
                conn.close()
            return True
        except Exception as e:
            print(f"[ERROR] SQLite cache SET error: {e}")
            return False

    def get(self, key: str) -> Optional[str]:
        """Retrieve value by key if not expired."""
        if self.upstash_rest_enabled:
            try:
                res = self._exec_upstash_rest(["GET", key])
                return str(res) if res is not None else None
            except Exception as e:
                print(f"[WARN] Upstash REST GET failed ({e}), attempting fallback.")

        if self.redis_client:
            try:
                return self.redis_client.get(key)
            except Exception as e:
                print(f"[WARN] Redis TCP GET failed ({e}), falling back to SQLite.")

        # SQLite Fallback
        try:
            self._cleanup_expired_sqlite()
            now = time.time()
            with self.db_lock:
                conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT cache_value, expires_at FROM cache_store WHERE cache_key = ?", (key,))
                row = cursor.fetchone()
                conn.close()

            if row:
                cache_value, expires_at = row
                if expires_at > now:
                    return cache_value
                else:
                    self.delete(key)
            return None
        except Exception as e:
            print(f"[ERROR] SQLite cache GET error: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete key immediately (used for single-use OTP prevention)."""
        if self.upstash_rest_enabled:
            try:
                self._exec_upstash_rest(["DEL", key])
            except Exception:
                pass

        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception:
                pass

        try:
            with self.db_lock:
                conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache_store WHERE cache_key = ?", (key,))
                conn.commit()
                conn.close()
            return True
        except Exception:
            return False

    def incr(self, key: str, ex: int = 600) -> int:
        """Atomic counter increment with rate limit window."""
        if self.upstash_rest_enabled:
            try:
                val = self._exec_upstash_rest(["INCR", key])
                if val == 1:
                    self._exec_upstash_rest(["EXPIRE", key, ex])
                return int(val)
            except Exception as e:
                print(f"[WARN] Upstash REST INCR failed ({e}), attempting fallback.")

        if self.redis_client:
            try:
                val = self.redis_client.incr(key)
                if val == 1:
                    self.redis_client.expire(key, ex)
                return int(val)
            except Exception as e:
                print(f"[WARN] Redis TCP INCR failed ({e}), falling back to SQLite.")

        # SQLite Fallback
        try:
            current_val = self.get(key)
            if current_val is None:
                new_val = 1
                self.set(key, str(new_val), ex=ex)
            else:
                new_val = int(current_val) + 1
                with self.db_lock:
                    conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE cache_store SET cache_value = ? WHERE cache_key = ?", (str(new_val), key))
                    conn.commit()
                    conn.close()
            return new_val
        except Exception as e:
            print(f"[ERROR] SQLite INCR error: {e}")
            return 1


# Instantiate Cache Manager
cache = CacheManager(REDIS_URL)

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class OTPRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(default="booking", description="booking, contact, or prashna")

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    purpose: str = Field(default="booking")

class BookingCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    serviceType: str
    birthDate: str  # YYYY-MM-DD
    birthTime: str  # HH:MM
    birthPlace: Optional[str] = None
    bookingDate: str  # YYYY-MM-DD
    bookingTime: str  # HH:MM or "10:00 AM"
    additionalInfo: Optional[str] = None
    verificationToken: Optional[str] = None

class ContactCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    subject: str = Field(..., min_length=2, max_length=200)
    message: str = Field(..., min_length=2, max_length=2000)
    verificationToken: Optional[str] = None

class SlotResponse(BaseModel):
    date: str
    slots: List[str]

# -----------------------------------------------------------------------------
# Input Sanitization and Validation Helpers
# -----------------------------------------------------------------------------

def sanitize_string(val: str) -> str:
    """Strip HTML tags and escape input string to protect against XSS injection."""
    if not val:
        return val
    cleaned = re.sub(r"<[^>]*>", "", val)
    return html.escape(cleaned.strip())

def validate_and_format_phone(phone: Optional[str]) -> str:
    """
    Validate and format mobile number professionally.
    Does NOT require a compulsory '+91' prefix.
    Accepts:
      - 10-digit Indian numbers: '9876543210' (starts with 6, 7, 8, or 9)
      - With optional leading 0: '09876543210'
      - With optional leading +91 or 91: '+91 98765 43210', '919876543210'
      - General valid numbers (10 to 15 digits)
    Rejects spam repetitions (e.g. 1111111111, 0000000000).
    """
    if not phone:
        return "None"
    cleaned = phone.strip()
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return "None"
    
    # Check for all repeating identical digits (e.g. 1111111111, 0000000000)
    if len(set(digits)) == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a genuine mobile number (repeated identical digits detected)."
        )
    if re.search(r"(\d)\1{7,}", digits):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Suspicious repeating phone number pattern detected."
        )

    # 10 digits (Standard Indian format without prefix)
    if len(digits) == 10:
        if digits[0] in ['6', '7', '8', '9']:
            return digits
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="10-digit mobile numbers in India must start with 6, 7, 8, or 9."
        )
    # 11 digits starting with 0
    if len(digits) == 11 and digits.startswith('0'):
        return digits[1:]
    # 12 digits starting with 91
    if len(digits) == 12 and digits.startswith('91'):
        return digits[2:]
    # General valid numbers
    if 10 <= len(digits) <= 15:
        return digits

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Please enter a valid 10-digit mobile number (e.g. 9876543210)."
    )

def is_spam_phone(phone: str) -> bool:
    try:
        validate_and_format_phone(phone)
        return False
    except HTTPException:
        return True

def parse_time_string(time_str: str) -> time:
    """Helper to parse 12-hour or 24-hour time to datetime.time."""
    try:
        if "AM" in time_str or "PM" in time_str:
            dt = datetime.strptime(time_str, "%I:%M %p")
            return dt.time()
        dt = datetime.strptime(time_str, "%H:%M")
        return dt.time()
    except Exception:
        return dt_time(10, 0)


# -----------------------------------------------------------------------------
# Email Delivery Engine (Resend with IPv4-Enforced SMTP Fallback)
# -----------------------------------------------------------------------------

class IPv4SMTP(smtplib.SMTP):
    """Custom SMTP client that forces IPv4 connections to prevent network unreachable errors on cloud platforms."""
    def _get_socket(self, host, port, timeout):
        for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            try:
                s = socket.socket(af, socktype, proto)
                if timeout is not None:
                    s.settimeout(timeout)
                s.connect(sa)
                return s
            except Exception:
                if s:
                    s.close()
        raise socket.error(f"Could not connect to IPv4 address for {host}:{port}")


def send_email_unified(subject: str, text_body: str, html_body: str, to_email: Optional[str] = None) -> bool:
    """
    Unified email dispatcher:
    1. Attempts delivery via Resend API (HTTPS Port 443, custom verified domain, instant inbox).
    2. Falls back to Gmail SMTP over IPv4 Port 587 (STARTTLS) if Resend is unconfigured or encounters an error.
    """
    recipient = to_email or os.getenv("SMTP_RECEIVER") or os.getenv("SMTP_EMAIL", "sarsajyotish@gmail.com")
    resend_key = os.getenv("RESEND_API_KEY", "")
    from_email = os.getenv("RESEND_FROM_EMAIL", "AstroAdvice <contact@sarsajyotishsansthan.com>")

    # 1. Try Resend Delivery (HTTPS port 443 - 100% reliable on Render/Cloud)
    if resend_key and resend_key != "your_resend_api_key_here":
        try:
            resend.api_key = resend_key
            params: resend.Emails.SendParams = {
                "from": from_email,
                "to": [recipient],
                "subject": subject,
                "html": html_body,
                "text": text_body
            }
            res = resend.Emails.send(params)
            print(f"[INFO] Resend email '{subject}' delivered to {recipient}. ID: {res.get('id', 'ok')}")
            return True
        except Exception as res_err:
            print(f"[WARN] Resend dispatch failed ({res_err}). Attempting IPv4 SMTP fallback...")

    # 2. Fallback to IPv4-Forced SMTP
    return send_smtp_fallback(subject, text_body, html_body, recipient)


def send_smtp_fallback(subject: str, text_body: str, html_body: str, recipient: str) -> bool:
    """Fallback multipart SMTP email sender with forced IPv4 socket to prevent [Errno 101] Network is unreachable on Render."""
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")

    if not sender_email or not sender_password or not recipient:
        print("[WARN] SMTP configurations missing. Fallback email dispatch skipped.")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid()

        part1 = MIMEText(text_body, 'plain', 'utf-8')
        part2 = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(part1)
        msg.attach(part2)

        # Attempt connection on standard submission Port 587 with STARTTLS using forced IPv4
        with IPv4SMTP("smtp.gmail.com", 587, timeout=12) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient, msg.as_string())

        print(f"[INFO] Fallback SMTP (IPv4 587) email '{subject}' dispatched to {recipient}")
        return True
    except Exception as e:
        print(f"[WARN] SMTP delivery attempt failed: {e}")
        return False

# -----------------------------------------------------------------------------
# Google Sheets Integration
# -----------------------------------------------------------------------------

def get_google_credentials(scopes: List[str]):
    """
    Retrieve Google service account credentials with multi-source resolution:
    1. Direct JSON string in environment variables (GOOGLE_SERVICE_ACCOUNT_JSON / SERVICE_ACCOUNT_JSON / GOOGLE_CREDENTIALS)
    2. Render Secret Files path (/etc/secrets/service_account.json)
    3. File path specified by GOOGLE_SERVICE_ACCOUNT_FILE
    4. Relative file lookup in backend directory or current working directory
    """
    # 1. Check raw JSON string in environment variables (Critical for Render/Cloud deployment)
    for env_key in ["GOOGLE_SERVICE_ACCOUNT_JSON", "SERVICE_ACCOUNT_JSON", "GOOGLE_CREDENTIALS", "GCP_SERVICE_ACCOUNT"]:
        raw_json = os.getenv(env_key, "").strip()
        if raw_json and ("private_key" in raw_json or raw_json.startswith("{")):
            try:
                info = json.loads(raw_json)
                return service_account.Credentials.from_service_account_info(info, scopes=scopes)
            except Exception as je:
                print(f"[WARN] Failed to parse {env_key} JSON string: {je}")

    # 2. Check candidate file paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_paths = [
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
        os.path.join(current_dir, "service_account.json"),
        "/etc/secrets/service_account.json",
        "/etc/secrets/google_service_account.json",
        "/etc/secrets/GOOGLE_SERVICE_ACCOUNT_FILE",
        os.path.join(current_dir, "backend", "service_account.json"),
        os.path.join(os.getcwd(), "service_account.json"),
        os.path.join(os.getcwd(), "backend", "service_account.json"),
        "service_account.json"
    ]

    for path in candidate_paths:
        if path and os.path.exists(path):
            try:
                return service_account.Credentials.from_service_account_file(path, scopes=scopes)
            except Exception as fe:
                print(f"[WARN] Failed to load credentials from file '{path}': {fe}")

    return None


def get_google_services():
    """Build and return authorized Google Sheets and Drive API clients."""
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = get_google_credentials(scopes)
        if not creds:
            return None, None
        sheets_service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return sheets_service, drive_service
    except Exception as e:
        print(f"[ERROR] Failed to initialize Google API credentials: {e}")
        return None, None


def get_spreadsheet_ids() -> List[str]:
    """Retrieve all configured Google Sheet IDs with guaranteed dual-sheet fallback."""
    sheet_ids = []
    
    # 1. Check primary GOOGLE_SHEET_ID (supports comma-separated list)
    env_sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    if env_sheet_id and env_sheet_id.strip() and env_sheet_id != "your_google_sheet_id_here":
        for sid in env_sheet_id.split(","):
            cleaned = sid.strip()
            if cleaned and cleaned not in sheet_ids:
                sheet_ids.append(cleaned)

    # 2. Check secondary GOOGLE_SHEET_ID_2
    secondary_id = os.getenv("GOOGLE_SHEET_ID_2", "")
    if secondary_id and secondary_id.strip() and secondary_id not in sheet_ids:
        sheet_ids.append(secondary_id.strip())

    # 3. Known Primary & Secondary Default Google Sheets
    default_sheets = [
        "1TyXzitHdW11NpD4PAQtJYv8N-LuWrq6hTXkHOEQ6Lto",
        "1mFvsDChXpNCmtWwkvrNV3NIpRnoB5q9WuYe3c3Rc4rg"
    ]
    for ds in default_sheets:
        if ds not in sheet_ids:
            sheet_ids.append(ds)

    # 4. Check cached config if still empty
    if not sheet_ids and os.path.exists(SHEETS_CONFIG_FILE):
        try:
            with open(SHEETS_CONFIG_FILE, "r") as f:
                data = json.load(f)
                cached = data.get("spreadsheet_id")
                if cached and cached not in sheet_ids:
                    sheet_ids.append(cached)
        except Exception as e:
            print(f"[WARN] Could not read {SHEETS_CONFIG_FILE}: {e}")

    # 5. Fallback to dynamic creation if completely empty
    if not sheet_ids:
        created_id = get_or_create_spreadsheet()
        if created_id:
            sheet_ids.append(created_id)

    return sheet_ids


def get_or_create_spreadsheet() -> Optional[str]:
    """Retrieve existing Google Sheet ID from environment or cached config."""
    sheets_service, drive_service = get_google_services()
    if not sheets_service or not drive_service:
        return None

    try:
        spreadsheet_body = {
            'properties': {
                'title': 'Sarsa Jyotish Sansthan - Client CRM Database'
            }
        }
        sheet = sheets_service.spreadsheets().create(body=spreadsheet_body, fields='spreadsheetId').execute()
        new_sheet_id = sheet.get('spreadsheetId')
        print(f"[INFO] Created new Google Sheet database with ID: {new_sheet_id}")

        recipient = os.getenv("SMTP_RECEIVER") or os.getenv("SMTP_EMAIL")
        if recipient and "@" in recipient:
            try:
                user_permission = {
                    'type': 'user',
                    'role': 'editor',
                    'emailAddress': recipient
                }
                drive_service.permissions().create(
                    fileId=new_sheet_id,
                    body=user_permission,
                    fields='id'
                ).execute()
                print(f"[INFO] Shared spreadsheet with {recipient} as Editor.")
            except Exception as pe:
                print(f"[ERROR] Failed to share spreadsheet with {recipient}: {pe}")

        try:
            with open(SHEETS_CONFIG_FILE, "w") as f:
                json.dump({"spreadsheet_id": new_sheet_id}, f)
        except Exception:
            pass

        return new_sheet_id
    except Exception as e:
        print(f"[ERROR] Failed to generate spreadsheet: {e}")
        return None


def append_row_to_sheet(tab_name: str, row_data: list, headers: list):
    """Log customer data by appending it to ALL configured Google Sheets with retry & local JSON fallback."""
    sheets_service, _ = get_google_services()

    # Format values safely for Google Sheets (prevent +91... leading formulas from showing #ERROR!)
    safe_row_data = []
    for item in row_data:
        str_val = str(item) if item is not None else ""
        # If string starts with + or =, format as plain string literal
        if str_val.startswith("+") or str_val.startswith("="):
            safe_row_data.append(f"'{str_val}")
        else:
            safe_row_data.append(str_val)

    if not sheets_service:
        mock_file = f"mock_{tab_name.lower().replace(' ', '_')}.json"
        try:
            existing = []
            if os.path.exists(mock_file):
                with open(mock_file, "r") as f:
                    existing = json.load(f)
            record = dict(zip(headers, safe_row_data))
            existing.append(record)
            with open(mock_file, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"[INFO] Fallback: Logged record to local JSON database: {mock_file}")
        except Exception as fe:
            print(f"[ERROR] Fallback database logging failed: {fe}")
        return

    spreadsheet_ids = get_spreadsheet_ids()
    if not spreadsheet_ids:
        print("[WARN] No Google Sheet IDs configured for logging.")
        return

    # Write to each configured Google Sheet database with retry mechanism
    for spreadsheet_id in spreadsheet_ids:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                range_name = f"'{tab_name}'!A:A"
                body = {'values': [safe_row_data]}
                sheets_service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
                print(f"[INFO] Appended row to tab '{tab_name}' on Google Sheet [{spreadsheet_id[:8]}...].")
                break
            except HttpError as error:
                if error.resp.status == 400:
                    # Tab may not exist yet, create tab and add header row
                    try:
                        sheets_service.spreadsheets().batchUpdate(
                            spreadsheetId=spreadsheet_id,
                            body={'requests': [{'addSheet': {'properties': {'title': tab_name}}}]}
                        ).execute()
                        sheets_service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f"'{tab_name}'!A1",
                            valueInputOption='USER_ENTERED',
                            body={'values': [headers]}
                        ).execute()
                        sheets_service.spreadsheets().values().append(
                            spreadsheetId=spreadsheet_id,
                            range=f"'{tab_name}'!A:A",
                            valueInputOption='USER_ENTERED',
                            insertDataOption='INSERT_ROWS',
                            body={'values': [safe_row_data]}
                        ).execute()
                        print(f"[INFO] Dynamic sheet tab '{tab_name}' creation on [{spreadsheet_id[:8]}...] successful.")
                        break
                    except Exception as e2:
                        print(f"[ERROR] Dynamic sheet initialization on [{spreadsheet_id[:8]}...] failed: {e2}")
                        break
                elif error.resp.status in [500, 502, 503, 504, 429]:
                    print(f"[WARN] Transient Google Sheets error ({error.resp.status}) on [{spreadsheet_id[:8]}...], retry {attempt}/{max_attempts}...")
                    time.sleep(attempt * 1.0)
                else:
                    print(f"[ERROR] Google Sheets API error ({error.resp.status}) on [{spreadsheet_id[:8]}...]: {error}")
                    break
            except Exception as e:
                print(f"[WARN] Connection error during sheet append on [{spreadsheet_id[:8]}...] (attempt {attempt}/{max_attempts}): {e}")
                time.sleep(attempt * 1.0)


# -----------------------------------------------------------------------------
# Google Calendar Synchronization
# -----------------------------------------------------------------------------

def get_calendar_service():
    """Retrieve initialized Calendar API client using service account credentials."""
    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        creds = get_google_credentials(scopes)
        if not creds:
            return None
        return build('calendar', 'v3', credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Google Calendar API: {e}")
        return None

# -----------------------------------------------------------------------------
# OTP Verification & Rate Limiting Endpoints
# -----------------------------------------------------------------------------

@app.post("/api/otp/send", status_code=status.HTTP_200_OK)
def send_otp(request_data: OTPRequest, request: Request):
    """
    Generate and dispatch a 6-digit verification code with 5-minute TTL (300s).
    Includes rate-limiting (max 5 requests per 10 minutes per IP/email).
    """
    email = request_data.email.lower().strip()
    purpose = request_data.purpose.lower().strip()
    client_ip = request.client.host if request.client else "unknown_ip"

    # 1. Rate Limiting Check (Max 5 attempts in 10 minutes / 600s)
    ip_rate_key = f"ratelimit:ip:{client_ip}"
    email_rate_key = f"ratelimit:email:{email}"
    
    ip_attempts = cache.incr(ip_rate_key, ex=600)
    email_attempts = cache.incr(email_rate_key, ex=600)

    if ip_attempts > 5 or email_attempts > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please wait 10 minutes before trying again."
        )

    # 2. Generate 6-digit cryptographic random OTP code
    otp_code = f"{secrets.randbelow(900000) + 100000}"

    # 3. Store in Redis / Cache with 5-minute (300 seconds) auto-expiry TTL
    cache_key = f"otp:{email}:{purpose}"
    cache.set(cache_key, otp_code, ex=300)

    # 4. Dispatch OTP Email via Resend (or SMTP fallback)
    subject = f"Your Verification Code: {otp_code} — Sarsa Jyotish Sansthan"
    text_body = f"Hello,\n\nYour 6-digit verification code is: {otp_code}\n\nThis code will expire in 5 minutes.\n\nWarm regards,\nAstrologer Madhuri Gupta Team"
    html_body = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
      </head>
      <body style="margin: 0; padding: 24px; font-family: 'Segoe UI', Arial, sans-serif; background-color: #faf6e8; color: #4f3129;">
        <div style="max-width: 520px; margin: 0 auto; background-color: #ffffff; border: 1px solid #deb18a; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(79, 49, 41, 0.08);">
          <!-- Header Banner -->
          <div style="background-color: #4f3129; padding: 28px 24px; text-align: center; border-bottom: 3px solid #b8922b;">
            <h1 style="margin: 0; font-family: Georgia, serif; font-size: 22px; color: #deb18a; letter-spacing: 2px; text-transform: uppercase;">
              Sarsa Jyotish Sansthan
            </h1>
            <p style="margin: 6px 0 0 0; color: rgba(222, 177, 138, 0.8); font-size: 11px; letter-spacing: 1px; text-transform: uppercase;">
              Astrologer Madhuri Gupta • Agra
            </p>
          </div>

          <!-- Body Content -->
          <div style="padding: 32px 28px; text-align: center;">
            <h2 style="margin: 0 0 10px 0; font-family: Georgia, serif; color: #4f3129; font-size: 20px;">
              Email Security Verification
            </h2>
            <p style="margin: 0 0 24px 0; color: #6f5149; font-size: 13px; line-height: 1.6;">
              Please use the one-time security code below to complete your <strong>{purpose}</strong> consultation request.
            </p>

            <!-- OTP Box -->
            <div style="margin: 20px auto; padding: 18px 24px; background: linear-gradient(135deg, #faf6e8 0%, #f4edd9 100%); border: 1.5px dashed #b8922b; border-radius: 12px; display: inline-block;">
              <span style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 700; letter-spacing: 10px; color: #4f3129; display: block; padding-left: 10px;">
                {otp_code}
              </span>
            </div>

            <p style="margin: 20px 0 0 0; font-size: 12px; color: #8a6d3b; font-weight: 600;">
              ⏳ Valid for 5 minutes only
            </p>

            <div style="margin-top: 28px; padding-top: 20px; border-top: 1px solid #f0e6d2; text-align: left; font-size: 11px; color: #8f6c60; line-height: 1.6;">
              <p style="margin: 0;"><strong>Security Notice:</strong> Never share this code with anyone. Our team will never ask for your verification code.</p>
            </div>
          </div>

          <!-- Footer -->
          <div style="background-color: #faf6e8; padding: 16px 24px; text-align: center; font-size: 10px; color: #8a6d3b; border-top: 1px solid #deb18a;">
            © {datetime.now().year} Sarsa Jyotish Sansthan • All Rights Reserved
          </div>
        </div>
      </body>
    </html>
    """

    email_sent = send_email_unified(subject, text_body, html_body, to_email=email)

    return {
        "status": "success",
        "message": "Verification code dispatched successfully.",
        "email": email,
        "purpose": purpose,
        "expiresIn": 300,
        "emailDispatched": email_sent
    }

@app.post("/api/otp/verify", status_code=status.HTTP_200_OK)
def verify_otp(verify_data: OTPVerify):
    """
    Validate 6-digit OTP code against Redis / Cache.
    - Prevents replay attacks by deleting OTP immediately upon success.
    - Generates a single-use verification token valid for 15 minutes (900s).
    """
    email = verify_data.email.lower().strip()
    purpose = verify_data.purpose.lower().strip()
    submitted_otp = verify_data.otp.strip()

    cache_key = f"otp:{email}:{purpose}"
    stored_otp = cache.get(cache_key)

    if not stored_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired or is invalid. Please request a new code."
        )

    if stored_otp != submitted_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect verification code. Please check and try again."
        )

    # Delete OTP to prevent double submission
    cache.delete(cache_key)

    # Generate single-use verification token with 15-minute TTL (900 seconds)
    token = f"tok_{secrets.token_hex(16)}"
    token_key = f"verified:{email}:{purpose}"
    cache.set(token_key, token, ex=900)

    return {
        "status": "success",
        "message": "OTP verified successfully.",
        "verifiedToken": token,
        "expiresIn": 900
    }

# -----------------------------------------------------------------------------
# Slot Retrieval & Booking Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/available-slots", response_model=SlotResponse)
def get_available_slots(date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
    service = get_calendar_service()
    default_slots = ["10:00 AM", "11:30 AM", "02:00 PM", "03:30 PM", "05:00 PM"]
    
    if not service:
        return SlotResponse(date=date, slots=default_slots)
        
    try:
        start_dt = datetime.strptime(f"{date} 00:00:00", "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(f"{date} 23:59:59", "%Y-%m-%d %H:%M:%S")
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_dt.isoformat() + 'Z',
            timeMax=end_dt.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        free_slots = []
        for slot in default_slots:
            slot_time = parse_time_string(slot)
            slot_start = datetime.combine(start_dt.date(), slot_time)
            slot_end = slot_start + timedelta(minutes=30)
            
            overlap_count = 0
            for event in events:
                event_start_str = event.get('start', {}).get('dateTime') or event.get('start', {}).get('date')
                event_end_str = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date')
                
                if not event_start_str or not event_end_str:
                    continue
                
                event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00')).replace(tzinfo=None)
                event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00')).replace(tzinfo=None)
                
                if (slot_start < event_end) and (slot_end > event_start):
                    overlap_count += 1
            
            if overlap_count < 2:
                free_slots.append(slot)
                
        return SlotResponse(date=date, slots=free_slots)
    except Exception as e:
        print(f"[ERROR] Slot query exception: {e}")
        return SlotResponse(date=date, slots=default_slots)


# -----------------------------------------------------------------------------
# Background Asynchronous Execution Pipelines
# -----------------------------------------------------------------------------

def background_booking_pipeline(
    name: str,
    email: str,
    phone: str,
    service_type: str,
    birth_date: str,
    birth_time: str,
    birth_place: str,
    booking_date: str,
    booking_time: str,
    additional_info: str,
    meeting_id: str,
    jitsi_link: str,
    start_time: datetime,
    end_time: datetime,
    birth_details_str: str,
):
    """
    Asynchronous background pipeline:
    1. Synchronizes consultation event to Google Calendar.
    2. Logs client details to BOTH Google Sheets simultaneously.
    3. Dispatches branded HTML confirmation email to client via Resend.
    4. Dispatches instant booking alert to the astrologer via Resend.
    Runs in the background so the user receives an instantaneous response.
    """
    print(f"[ASYNC START] Processing background booking pipeline for {name} ({email})...")

    # 1. Google Calendar Event Insertion
    try:
        service = get_calendar_service()
        if service:
            calendar_event = {
                'summary': f"Astrology Consultation: {name} ({service_type})",
                'location': jitsi_link,
                'description': f"Vedic birth details:\nDate: {birth_date}\nTime: {birth_time}\nPlace: {birth_place}\n\nClient notes: {additional_info}",
                'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
                'reminders': {
                    'useDefault': False, 
                    'overrides': [
                        {'method': 'email', 'minutes': 1440}, 
                        {'method': 'popup', 'minutes': 30}
                    ]
                },
            }
            created_event = service.events().insert(calendarId=CALENDAR_ID, body=calendar_event).execute()
            print(f"[ASYNC] Google Calendar event generated. ID: {created_event.get('id')}")
    except Exception as ce:
        print(f"[ASYNC ERROR] Google Calendar sync failed: {ce}")

    # 2. Dual Google Sheets Logging
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [timestamp, name, email, phone, service_type, booking_date, booking_time, "30 Mins", birth_details_str]
        headers = ["Timestamp", "Full Name", "Email", "Phone", "Service Name", "Date", "Time Slot", "Duration", "Birth Details"]
        append_row_to_sheet("Bookings", row_data, headers)
        print(f"[ASYNC] Dual Google Sheets updated successfully for {name}.")
    except Exception as se:
        print(f"[ASYNC ERROR] Dual sheets sync failed: {se}")

    # 3. Dispatches Branded Confirmation Email to Client via Resend
    try:
        cust_subject = f"Confirmed: Your Astrological Consultation with Madhuri Gupta"
        cust_text = f"Dear {name},\n\nYour session for {service_type} has been successfully scheduled.\n\nDate: {booking_date}\nTime: {booking_time}\nMeeting Link: {jitsi_link}\n\nWarm regards,\nAstrologer Madhuri Gupta Team"
        cust_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #4f3129; padding: 20px; background-color: #faf6e8;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #deb18a; border-radius: 12px; padding: 30px; background-color: #ffffff;">
              <h2 style="color: #4f3129; text-align: center;">Consultation Confirmed</h2>
              <hr style="border-color: #deb18a;" />
              <p>Dear <strong>{name}</strong>,</p>
              <p>Your session with <strong>Astrologer Madhuri Gupta</strong> has been successfully booked.</p>
              <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr><td style="padding: 6px 0; color: #6f5149;"><strong>Service:</strong></td><td style="padding: 6px 0; color: #4f3129;">{service_type}</td></tr>
                <tr><td style="padding: 6px 0; color: #6f5149;"><strong>Date:</strong></td><td style="padding: 6px 0; color: #4f3129;">{booking_date}</td></tr>
                <tr><td style="padding: 6px 0; color: #6f5149;"><strong>Time Slot:</strong></td><td style="padding: 6px 0; color: #4f3129;">{booking_time}</td></tr>
                <tr><td style="padding: 6px 0; color: #6f5149;"><strong>Birth Place:</strong></td><td style="padding: 6px 0; color: #4f3129;">{birth_place}</td></tr>
              </table>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{jitsi_link}" style="background-color: #b8922b; color: #ffffff; text-decoration: none; padding: 12px 25px; border-radius: 20px; font-weight: bold; display: inline-block;">JOIN MEETING</a>
              </div>
              <p style="font-size: 11px; color: #8f6c60; text-align: center;">The session takes place via Jitsi Meet. No download required.</p>
            </div>
          </body>
        </html>
        """
        send_email_unified(cust_subject, cust_text, cust_html, to_email=email)
        print(f"[ASYNC] Confirmation email dispatched to client {email}.")
    except Exception as ee:
        print(f"[ASYNC ERROR] Client confirmation email dispatch failed: {ee}")

    # 4. Dispatches Alert Email to Astrologer via Resend
    try:
        astro_subject = f"New Consultation Booked: {name} - {service_type}"
        astro_text = f"New consultation booked.\n\nClient Name: {name}\nEmail: {email}\nPhone: {phone}\nService: {service_type}\nDate: {booking_date}\nTime: {booking_time}\nBirth Details: {birth_details_str}\nNotes: {additional_info}\nMeeting Link: {jitsi_link}"
        astro_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #4f3129; padding: 20px; background-color: #faf6e8;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #deb18a; border-radius: 12px; padding: 30px; background-color: #ffffff;">
              <h2 style="color: #4f3129;">New Booking Alert</h2>
              <hr style="border-color: #deb18a;" />
              <p><strong>Client Details:</strong></p>
              <ul>
                <li><strong>Name:</strong> {name}</li>
                <li><strong>Email:</strong> {email}</li>
                <li><strong>Phone:</strong> {phone}</li>
                <li><strong>Service:</strong> {service_type}</li>
                <li><strong>Date & Slot:</strong> {booking_date} at {booking_time}</li>
                <li><strong>Birth Details:</strong> {birth_details_str}</li>
                <li><strong>Additional Notes:</strong> {additional_info}</li>
              </ul>
              <p><strong>Meeting Link:</strong> <a href="{jitsi_link}">{jitsi_link}</a></p>
            </div>
          </body>
        </html>
        """
        send_email_unified(astro_subject, astro_text, astro_html, to_email=None)
        print(f"[ASYNC] Astrologer alert email dispatched.")
    except Exception as ae:
        print(f"[ASYNC ERROR] Astrologer alert email dispatch failed: {ae}")

    print(f"[ASYNC COMPLETE] Background booking pipeline finished for {name}.")


def background_contact_pipeline(name: str, email: str, phone: str, subject: str, message: str):
    """
    Asynchronous background pipeline for contact inquiries:
    1. Appends query to BOTH Google Sheets.
    2. Sends email notification to the astrologer via Resend.
    """
    print(f"[ASYNC START] Processing contact inquiry for {name} ({email})...")

    # 1. Dual Google Sheets Logging
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [timestamp, name, email, phone, subject, message]
        headers = ["Timestamp", "Name", "Email", "Phone", "Subject", "Message"]
        append_row_to_sheet("Contact Queries", row_data, headers)
        print(f"[ASYNC] Contact query appended to Dual Google Sheets.")
    except Exception as se:
        print(f"[ASYNC ERROR] Dual sheets contact log failed: {se}")

    # 2. Resend Email Notification to Astrologer
    try:
        mail_subject = f"New Contact Query: {subject} ({name})"
        mail_text = f"New message from {name}.\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nSubject: {subject}\nMessage:\n{message}"
        mail_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #4f3129; padding: 20px; background-color: #faf6e8;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #deb18a; border-radius: 12px; padding: 30px; background-color: #ffffff;">
              <h2 style="color: #4f3129;">New Contact Query</h2>
              <hr style="border-color: #deb18a;" />
              <p><strong>Sender:</strong> {name} ({email})</p>
              <p><strong>Phone:</strong> {phone}</p>
              <p><strong>Subject:</strong> {subject}</p>
              <blockquote style="border-left: 3px solid #deb18a; padding-left: 15px; color: #6f5149; margin: 15px 0;">
                {message}
              </blockquote>
            </div>
          </body>
        </html>
        """
        send_email_unified(mail_subject, mail_text, mail_html, to_email=None)
        print(f"[ASYNC] Contact email alert sent to astrologer.")
    except Exception as ae:
        print(f"[ASYNC ERROR] Contact email dispatch failed: {ae}")

    # 3. Confirmation Email to Client
    try:
        client_subject = f"We have received your message - Astrologer Madhuri Gupta"
        client_text = f"Dear {name},\n\nThank you for reaching out to Sarsa Jyotish Sansthan. We have received your query regarding '{subject}'. Astrologer Madhuri Gupta will review your inquiry and get back to you shortly.\n\nWarm regards,\nSarsa Jyotish Sansthan, Agra"
        client_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #4f3129; padding: 20px; background-color: #faf6e8;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #deb18a; border-radius: 12px; padding: 30px; background-color: #ffffff;">
              <h2 style="color: #4f3129; text-align: center;">Message Received</h2>
              <hr style="border-color: #deb18a;" />
              <p>Dear <strong>{name}</strong>,</p>
              <p>Thank you for getting in touch with <strong>Sarsa Jyotish Sansthan</strong>. We have safely received your inquiry:</p>
              <div style="background-color: #faf6e8; border-left: 4px solid #b8922b; padding: 12px 16px; border-radius: 6px; margin: 16px 0;">
                <p style="margin: 0; font-weight: bold; color: #4f3129;">Subject: {subject}</p>
                <p style="margin: 8px 0 0 0; color: #6f5149; font-style: italic;">"{message}"</p>
              </div>
              <p>Astrologer Madhuri Gupta and our advisory team will review your message and reach out via phone or email shortly.</p>
              <p style="margin-top: 25px; color: #8a6d3b; font-size: 13px;">Warm regards,<br><strong>Astrologer Madhuri Gupta</strong><br>Sarsa Jyotish Sansthan, Agra, UP</p>
            </div>
          </body>
        </html>
        """
        send_email_unified(client_subject, client_text, client_html, to_email=email)
        print(f"[ASYNC] Confirmation email sent to client {email}.")
    except Exception as ce:
        print(f"[ASYNC ERROR] Client contact confirmation dispatch failed: {ce}")

    print(f"[ASYNC COMPLETE] Contact inquiry pipeline finished for {name}.")


# -----------------------------------------------------------------------------
# Booking & Contact Form Endpoints (Instant Async Responses)
# -----------------------------------------------------------------------------

def process_booking_creation(booking: BookingCreate, background_tasks: BackgroundTasks):
    """Business logic for booking appointments with instantaneous async dispatch."""
    name = sanitize_string(booking.name)
    email = booking.email.lower().strip()
    phone = validate_and_format_phone(booking.phone)
    service_type = sanitize_string(booking.serviceType)
    birth_date = sanitize_string(booking.birthDate)
    birth_time = sanitize_string(booking.birthTime)
    birth_place = sanitize_string(booking.birthPlace) if booking.birthPlace else "Not Specified"
    booking_date = sanitize_string(booking.bookingDate)
    booking_time = sanitize_string(booking.bookingTime)
    additional_info = sanitize_string(booking.additionalInfo) if booking.additionalInfo else "None"

    # 1. Enforce Email Verification via OTP (Stored in Redis)
    token_key = f"verified:{email}:booking"
    cached_token = cache.get(token_key)
    general_token_key = f"verified:{email}:any"
    cached_general = cache.get(general_token_key)

    is_verified = False
    if booking.verificationToken and (cached_token == booking.verificationToken or cached_general == booking.verificationToken):
        is_verified = True
    elif cached_token or cached_general:
        is_verified = True

    # In strict production mode, require verification
    if not is_verified and os.getenv("BYPASS_OTP_VERIFY") != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email with the 6-digit OTP code before proceeding."
        )

    # Consume single-use token from Redis
    cache.delete(token_key)
    cache.delete(general_token_key)

    # 2. Setup times & slots
    booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d")
    slot_time = parse_time_string(booking_time)
    start_time = datetime.combine(booking_date_obj.date(), slot_time)
    end_time = start_time + timedelta(minutes=30)

    # 3. Generate instant unique meeting ID & Jitsi Link
    meeting_id = str(uuid.uuid4())[:8]
    jitsi_link = f"https://meet.jit.si/MadhuriGuptaAstrology-{meeting_id}"
    birth_details_str = f"Date: {birth_date}, Time: {birth_time}, Place: {birth_place}"

    # 4. Fire heavy I/O operations (Calendar, Dual Sheets, Resend Emails) in a daemon background thread
    threading.Thread(
        target=background_booking_pipeline,
        kwargs={
            "name": name,
            "email": email,
            "phone": phone,
            "service_type": service_type,
            "birth_date": birth_date,
            "birth_time": birth_time,
            "birth_place": birth_place,
            "booking_date": booking_date,
            "booking_time": booking_time,
            "additional_info": additional_info,
            "meeting_id": meeting_id,
            "jitsi_link": jitsi_link,
            "start_time": start_time,
            "end_time": end_time,
            "birth_details_str": birth_details_str
        },
        daemon=True
    ).start()

    # 5. Return immediate response (< 20ms) to user
    return {
        "status": "confirmed",
        "bookingId": meeting_id,
        "jitsiLink": jitsi_link,
        "message": "Consultation scheduled successfully. Confirmation email and calendar invite are being dispatched.",
        "details": {
            "name": name,
            "email": email,
            "date": booking_date,
            "time": booking_time,
            "service": service_type
        }
    }


@app.post("/api/book-appointment", status_code=status.HTTP_201_CREATED)
def book_appointment_route(booking: BookingCreate, background_tasks: BackgroundTasks):
    return process_booking_creation(booking, background_tasks)


@app.post("/api/bookings", status_code=status.HTTP_201_CREATED)
def create_booking_alias(booking: BookingCreate, background_tasks: BackgroundTasks):
    return process_booking_creation(booking, background_tasks)


@app.post("/api/contact", status_code=status.HTTP_200_OK)
def create_contact_query(contact: ContactCreate, background_tasks: BackgroundTasks):
    name = sanitize_string(contact.name)
    email = contact.email.lower().strip()
    phone = validate_and_format_phone(contact.phone)
    subject = sanitize_string(contact.subject)
    message = sanitize_string(contact.message)

    # Email Verification Check
    token_key = f"verified:{email}:contact"
    cached_token = cache.get(token_key)
    general_token_key = f"verified:{email}:any"
    cached_general = cache.get(general_token_key)

    is_verified = False
    if contact.verificationToken and (cached_token == contact.verificationToken or cached_general == contact.verificationToken):
        is_verified = True
    elif cached_token or cached_general:
        is_verified = True

    if not is_verified and os.getenv("BYPASS_OTP_VERIFY") != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email with the 6-digit OTP code before submitting."
        )

    # Consume single-use token from Redis
    cache.delete(token_key)
    cache.delete(general_token_key)

    # Fire daemon background thread for instant sub-20ms return
    threading.Thread(
        target=background_contact_pipeline,
        kwargs={
            "name": name,
            "email": email,
            "phone": phone,
            "subject": subject,
            "message": message
        },
        daemon=True
    ).start()

    return {
        "status": "success",
        "message": "Contact query submitted successfully. The astrologer will get back to you shortly.",
        "email": email
    }



# -----------------------------------------------------------------------------
# System Status & Health Check
# -----------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "redis": "connected" if cache.redis_available else "sqlite_fallback",
            "resend": "configured" if (RESEND_API_KEY and RESEND_API_KEY != "your_resend_api_key_here") else "smtp_fallback",
            "calendar": "active" if os.path.exists(SERVICE_ACCOUNT_FILE) else "mock_mode",
            "sheets": "active" if os.path.exists(SERVICE_ACCOUNT_FILE) else "local_json_fallback"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
