import json
import os
import re
import secrets
import asyncio
import base64
import ctypes
import hashlib
import hmac
import subprocess
import tempfile
import sys
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from dotenv import load_dotenv
import edge_tts

try:
    from win10toast import ToastNotifier
except Exception:  # pragma: no cover - optional runtime dependency
    ToastNotifier = None  # type: ignore[assignment]

load_dotenv(override=True)

from .database import (
    get_db,
    Base,
    engine,
    ChatMessage,
    Memory,
    Task,
    InboxMessage,
    UserProfile,
    IntegrationConnection,
    SpeakerProfile,
)
from .ai_engine import generate_chat_stream, analyze_intent_and_memory
from .automation import execute_desktop_command

app = FastAPI(title="Akansha AI Engine")
planner_reminder_registry: dict[str, dict[str, Any]] = {}
planner_scheduler_task: asyncio.Task | None = None
planner_reminder_history: list[dict[str, Any]] = []
toast_notifier = ToastNotifier() if ToastNotifier else None
REMINDER_MARKER_DIR = Path(tempfile.gettempdir()) / "akansha-reminders"

# @app.on_event("startup")
# def reset_database():
#     import traceback
#     try:
#         Base.metadata.drop_all(bind=engine)
#         Base.metadata.create_all(bind=engine)
#         print("Successfully reset the database schema!")
#     except Exception as e:
#         print("Failed to reset database schema:", e)
#         traceback.print_exc()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    user_tone: str | None = None
    response_style: str | None = None
    conversation_mode: str | None = None
    language_preference: str | None = None


class ChatMessageSaveRequest(BaseModel):
    role: str
    content: str
    session_id: str


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    preferred_mode: str | None = None
    voice_gender: str | None = None
    voice_tone: str | None = None
    voice_language: str | None = None
    avatar_style: str | None = None
    background_listening: bool | None = None
    interrupt_enabled: bool | None = None
    username: str | None = None
    password: str | None = None


class ReminderRequest(BaseModel):
    title: str
    date_time: str


class SocialReplyRequest(BaseModel):
    message_id: int | None = None
    platform: str
    sender: str
    reply: str
    approved: bool = False


class SocialSetupRequest(BaseModel):
    config: dict[str, str]
    test_connection: bool = True


class TTSRequest(BaseModel):
    text: str
    voice_gender: str = "female"
    voice_tone: str | None = None
    language_mode: str | None = None


class DesktopNotificationRequest(BaseModel):
    title: str
    body: str


class PlannerReminderSyncItem(BaseModel):
    reminder_id: str
    title: str
    body: str
    reminder_at: str


class PlannerReminderSyncRequest(BaseModel):
    reminders: list[PlannerReminderSyncItem]


class BrowserAutomationPermissionsRequest(BaseModel):
    open_links: bool | None = None
    open_close_tabs: bool | None = None
    type_into_page: bool | None = None
    edit_fields: bool | None = None
    delete_draft_content: bool | None = None
    background_open: bool | None = None


class BrowserAutomationRunRequest(BaseModel):
    action: str
    target: str | None = None
    run_at: str | None = None
    background: bool = False


class BrowserAutomationPromptRequest(BaseModel):
    prompt: str
    run_at: str | None = None
    background: bool = True


class SpeakerProfileRequest(BaseModel):
    display_name: str
    relationship_to_owner: str | None = None
    access_level: str | None = None
    notes: str | None = None


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/google/callback")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def get_or_create_profile(db: Session) -> UserProfile:
    profile = db.query(UserProfile).first()
    if profile:
        return profile

    profile = UserProfile()
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def get_or_create_connection(db: Session, provider: str) -> IntegrationConnection:
    connection = db.query(IntegrationConnection).filter(IntegrationConnection.provider == provider).first()
    if connection:
        return connection

    connection = IntegrationConnection(provider=provider)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def serialize_profile(profile: UserProfile) -> dict[str, Any]:
    return {
        "full_name": profile.full_name,
        "email": profile.email,
        "preferred_mode": profile.preferred_mode,
        "voice_gender": profile.voice_gender,
        "voice_tone": profile.voice_tone,
        "voice_language": profile.voice_language or "telugu_english",
        "avatar_style": profile.avatar_style,
        "background_listening": profile.background_listening,
        "interrupt_enabled": profile.interrupt_enabled,
        "google_connected": profile.google_connected,
        "google_email": profile.google_email,
        "username": profile.username,
    }


def serialize_speaker_profile(profile: SpeakerProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "relationship_to_owner": profile.relationship_to_owner,
        "access_level": profile.access_level,
        "notes": profile.notes,
        "last_intro_text": profile.last_intro_text,
        "timestamp": profile.timestamp.isoformat() if profile.timestamp else None,
    }


def _speaker_access_level(relationship: str | None) -> str:
    normalized = (relationship or "").strip().lower()
    if normalized in {"owner", "self", "me", "myself"}:
        return "owner"
    if normalized in {"mother", "mom", "mummy", "amma", "father", "dad", "nanna", "sister", "brother", "wife", "husband", "friend"}:
        return "trusted"
    return "guest"


def _schedule_automation_plan(run_at_iso: str, plan: dict[str, Any], original_prompt: str) -> str:
    payload_dir = Path(tempfile.gettempdir()) / "akansha-automation"
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload_path = payload_dir / f"automation-{secrets.token_hex(8)}.json"
    payload_path.write_text(
        json.dumps(
            {
                "run_at": run_at_iso,
                "plan": plan,
                "prompt": original_prompt,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    subprocess.Popen(
        [sys.executable, "-m", "backend.scheduled_automation_runner", str(payload_path)],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return str(payload_path)


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)


def cloned_voice_configured() -> bool:
    return bool(ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)


def detect_text_language_mode(text: str) -> str:
    telugu_chars = len(re.findall(r"[\u0C00-\u0C7F]", text))
    hindi_chars = len(re.findall(r"[\u0900-\u097F]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if hindi_chars and latin_chars:
        return "hindi"
    if hindi_chars:
        return "hindi"
    if telugu_chars and latin_chars:
        return "mixed"
    if telugu_chars:
        return "telugu"
    return "english"


def build_voice_settings(voice_tone: str | None) -> dict[str, float]:
    tone = (voice_tone or "friendly").lower()
    if tone == "energetic":
        return {"stability": 0.38, "similarity_boost": 0.82, "style": 0.7, "use_speaker_boost": True}
    if tone == "calm":
        return {"stability": 0.72, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}
    if tone == "professional":
        return {"stability": 0.64, "similarity_boost": 0.84, "style": 0.28, "use_speaker_boost": True}
    return {"stability": 0.52, "similarity_boost": 0.83, "style": 0.45, "use_speaker_boost": True}


def get_edge_voice_name(voice_gender: str, language_mode: str) -> str:
    normalized_gender = (voice_gender or "female").lower()
    normalized_mode = (language_mode or "english").lower()

    telugu_voice = "te-IN-ShrutiNeural" if normalized_gender == "female" else "te-IN-MohanNeural"
    english_voice = "en-IN-NeerjaNeural" if normalized_gender == "female" else "en-IN-PrabhatNeural"
    hindi_voice = "hi-IN-SwaraNeural" if normalized_gender == "female" else "hi-IN-MadhurNeural"

    if normalized_mode == "hindi":
        return hindi_voice
    if normalized_mode in {"telugu", "mixed"}:
        return telugu_voice
    return english_voice


def get_edge_tts_prosody(voice_tone: str | None) -> tuple[str, str]:
    tone = (voice_tone or "friendly").lower()
    if tone == "energetic":
        return "+8%", "+4Hz"
    if tone == "calm":
        return "-10%", "-2Hz"
    if tone == "professional":
        return "-2%", "-1Hz"
    return "+0%", "+0Hz"


async def generate_edge_tts_audio(text: str, voice_gender: str, voice_tone: str | None, language_mode: str | None) -> bytes:
    resolved_mode = language_mode or detect_text_language_mode(text)
    voice_name = get_edge_voice_name(voice_gender, resolved_mode)
    rate, pitch = get_edge_tts_prosody(voice_tone)

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice_name,
        rate=rate,
        pitch=pitch,
    )

    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    if not audio_chunks:
        raise HTTPException(status_code=502, detail="Edge TTS did not return audio.")

    return b"".join(audio_chunks)


def show_windows_notification(title: str, body: str) -> None:
    clean_title = normalize_reminder_text(title) or "Akansha reminder"
    clean_body = normalize_reminder_text(body) or "You asked Akansha to remind you."

    if toast_notifier is not None:
        try:
            toast_notifier.show_toast(
                clean_title,
                clean_body,
                duration=10,
                threaded=False,
            )
            return
        except Exception:
            pass

    safe_title = clean_title.replace("'", "''")
    safe_body = clean_body.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = "<toast><visual><binding template='ToastGeneric'><text>{safe_title}</text><text>{safe_body}</text></binding></visual><audio silent='false'/></toast>"
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Akansha Planner').Show($toast)
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    popup_script = f"""
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName WindowsBase

$window = New-Object System.Windows.Window
$window.Title = 'Akansha reminder'
$window.Width = 420
$window.Height = 180
$window.Topmost = $true
$window.ResizeMode = 'NoResize'
$window.WindowStartupLocation = 'Manual'
$window.Left = [System.Windows.SystemParameters]::WorkArea.Right - 440
$window.Top = [System.Windows.SystemParameters]::WorkArea.Bottom - 220
$window.Background = '#111827'
$window.Foreground = '#F8FAFC'

$stack = New-Object System.Windows.Controls.StackPanel
$stack.Margin = '18'

$titleBlock = New-Object System.Windows.Controls.TextBlock
$titleBlock.Text = '{safe_title}'
$titleBlock.FontSize = 18
$titleBlock.FontWeight = 'Bold'
$titleBlock.Margin = '0,0,0,10'
$titleBlock.TextWrapping = 'Wrap'
$stack.Children.Add($titleBlock) | Out-Null

$bodyBlock = New-Object System.Windows.Controls.TextBlock
$bodyBlock.Text = '{safe_body}'
$bodyBlock.FontSize = 13
$bodyBlock.Foreground = '#CBD5E1'
$bodyBlock.TextWrapping = 'Wrap'
$stack.Children.Add($bodyBlock) | Out-Null

$window.Content = $stack

$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromSeconds(12)
$timer.Add_Tick({{
    $timer.Stop()
    $window.Close()
}})
$timer.Start()

$window.ShowDialog() | Out-Null
"""
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-Sta", "-Command", popup_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def normalize_reminder_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _powershell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _reminder_marker_path(reminder_id: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", reminder_id).strip("._") or "reminder"
    return REMINDER_MARKER_DIR / f"{safe_name}.json"


def _write_reminder_marker(reminder_id: str, title: str, body: str, reminder_at: str) -> Path:
    REMINDER_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    marker_path = _reminder_marker_path(reminder_id)
    marker_path.write_text(
        json.dumps(
            {
                "reminder_id": reminder_id,
                "title": normalize_reminder_text(title),
                "body": normalize_reminder_text(body),
                "reminder_at": reminder_at,
                "armed_at": datetime.now().astimezone().isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return marker_path


def _delete_reminder_marker(reminder_id: str) -> None:
    with suppress(FileNotFoundError):
        _reminder_marker_path(reminder_id).unlink()


def arm_detached_windows_reminder(reminder_id: str, title: str, body: str, reminder_at: str) -> dict[str, Any]:
    marker_path = _write_reminder_marker(reminder_id, title, body, reminder_at)
    now = datetime.now().astimezone()
    trigger_at = datetime.fromisoformat(reminder_at)
    if trigger_at.tzinfo is None:
        trigger_at = trigger_at.replace(tzinfo=now.tzinfo)
    delay_seconds = max(0, int((trigger_at - now).total_seconds()))

    expected_at = reminder_at.replace("'", "''")
    marker_literal = _powershell_single_quote(str(marker_path))
    popup_title = _powershell_single_quote(normalize_reminder_text(title) or "Akansha reminder")
    popup_body = _powershell_single_quote(normalize_reminder_text(body) or "You asked Akansha to remind you.")
    script = f"""
Start-Sleep -Seconds {delay_seconds}
try {{
    if (!(Test-Path -LiteralPath {marker_literal})) {{ exit }}
    $marker = Get-Content -Raw -LiteralPath {marker_literal} | ConvertFrom-Json
    if ($marker.reminder_at -ne '{expected_at}') {{ exit }}
    [System.Media.SystemSounds]::Exclamation.Play()
    Add-Type -AssemblyName PresentationFramework
    Add-Type -AssemblyName WindowsBase

    $window = New-Object System.Windows.Window
    $window.Title = 'Akansha reminder'
    $window.Width = 460
    $window.Height = 190
    $window.Topmost = $true
    $window.ResizeMode = 'NoResize'
    $window.WindowStartupLocation = 'Manual'
    $window.Left = [System.Windows.SystemParameters]::WorkArea.Right - 480
    $window.Top = [System.Windows.SystemParameters]::WorkArea.Bottom - 240
    $window.Background = '#101827'
    $window.Foreground = '#F8FAFC'

    $stack = New-Object System.Windows.Controls.StackPanel
    $stack.Margin = '20'

    $titleBlock = New-Object System.Windows.Controls.TextBlock
    $titleBlock.Text = {popup_title}
    $titleBlock.FontSize = 19
    $titleBlock.FontWeight = 'Bold'
    $titleBlock.Margin = '0,0,0,10'
    $titleBlock.TextWrapping = 'Wrap'
    $stack.Children.Add($titleBlock) | Out-Null

    $bodyBlock = New-Object System.Windows.Controls.TextBlock
    $bodyBlock.Text = {popup_body}
    $bodyBlock.FontSize = 13
    $bodyBlock.Foreground = '#CBD5E1'
    $bodyBlock.TextWrapping = 'Wrap'
    $stack.Children.Add($bodyBlock) | Out-Null

    $button = New-Object System.Windows.Controls.Button
    $button.Content = 'Dismiss'
    $button.Margin = '0,16,0,0'
    $button.Padding = '18,8'
    $button.HorizontalAlignment = 'Right'
    $button.Add_Click({{ $window.Close() }})
    $stack.Children.Add($button) | Out-Null

    $window.Content = $stack
    $timer = New-Object System.Windows.Threading.DispatcherTimer
    $timer.Interval = [TimeSpan]::FromSeconds(30)
    $timer.Add_Tick({{ $timer.Stop(); $window.Close() }})
    $timer.Start()
    $window.ShowDialog() | Out-Null
}} finally {{
    Remove-Item -LiteralPath {marker_literal} -Force -ErrorAction SilentlyContinue
}}
"""
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return {"pid": process.pid, "armed_for": reminder_at, "delay_seconds": delay_seconds}


async def planner_reminder_scheduler_loop() -> None:
    while True:
        now = datetime.now().astimezone()
        due_ids: list[str] = []

        for reminder_id, payload in list(planner_reminder_registry.items()):
            if payload.get("sent"):
                continue

            try:
                trigger_at = datetime.fromisoformat(str(payload["reminder_at"]))
            except Exception:
                continue

            if trigger_at.tzinfo is None:
                trigger_at = trigger_at.replace(tzinfo=now.tzinfo)

            if trigger_at <= now:
                clean_title = normalize_reminder_text(str(payload["title"]))
                clean_body = normalize_reminder_text(str(payload["body"]))
                try:
                    show_windows_notification(clean_title, clean_body)
                    planner_reminder_history.append({
                        "reminder_id": reminder_id,
                        "title": clean_title,
                        "body": clean_body,
                        "triggered_at": now.isoformat(),
                        "status": "sent",
                    })
                except Exception as exc:
                    planner_reminder_history.append({
                        "reminder_id": reminder_id,
                        "title": clean_title,
                        "body": clean_body,
                        "triggered_at": now.isoformat(),
                        "status": f"error: {exc}",
                    })
                due_ids.append(reminder_id)

        for reminder_id in due_ids:
            if reminder_id in planner_reminder_registry:
                planner_reminder_registry[reminder_id]["sent"] = True
                _delete_reminder_marker(reminder_id)

        await asyncio.sleep(1)


@app.on_event("startup")
async def startup_planner_scheduler() -> None:
    global planner_scheduler_task
    if planner_scheduler_task is None or planner_scheduler_task.done():
        planner_scheduler_task = asyncio.create_task(planner_reminder_scheduler_loop())


@app.on_event("shutdown")
async def shutdown_planner_scheduler() -> None:
    global planner_scheduler_task
    if planner_scheduler_task is not None:
        planner_scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await planner_scheduler_task
        planner_scheduler_task = None


def generate_cloned_voice_audio(text: str, voice_tone: str | None) -> bytes:
    if not cloned_voice_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Cloned female voice is not configured. Add ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID "
                "for the Irina voice clone."
            ),
        )

    payload = json.dumps(
        {
            "text": text,
            "model_id": ELEVENLABS_MODEL_ID,
            "voice_settings": build_voice_settings(voice_tone),
        }
    ).encode("utf-8")

    request = Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128",
        data=payload,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY or "",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            return response.read()
    except HTTPError as exc:
        detail = "Cloned voice request failed."
        try:
            provider_error = exc.read().decode("utf-8", errors="ignore")
            if provider_error:
                detail = provider_error
        except Exception:
            pass

        raise HTTPException(
            status_code=exc.code if exc.code else 502,
            detail=f"ElevenLabs voice synthesis failed: {detail}",
        )


def google_auth_headers(connection: IntegrationConnection) -> dict[str, str]:
    if not connection.access_token:
        raise HTTPException(status_code=400, detail="Google account is not connected yet.")
    return {"Authorization": f"Bearer {connection.access_token}"}


def google_api_get(url: str, connection: IntegrationConnection) -> Any:
    request = Request(url, headers=google_auth_headers(connection))
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def update_google_connection(
    db: Session,
    connection: IntegrationConnection,
    profile: UserProfile,
    token_payload: dict[str, Any],
    user_info: dict[str, Any] | None = None,
):
    expires_in = token_payload.get("expires_in", 0)
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None

    connection.access_token = token_payload.get("access_token")
    connection.refresh_token = token_payload.get("refresh_token") or connection.refresh_token
    connection.scope = token_payload.get("scope")
    connection.token_expiry = expiry
    connection.is_connected = True
    connection.account_email = (user_info or {}).get("email") or connection.account_email
    connection.metadata_json = json.dumps(
        {
            "token_type": token_payload.get("token_type", "Bearer"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    profile.google_connected = True
    profile.google_email = connection.account_email

    db.add(connection)
    db.add(profile)
    db.commit()


SOCIAL_PLATFORM_META: dict[str, dict[str, str]] = {
    "whatsapp": {"label": "WhatsApp", "accent": "#25D366"},
    "instagram": {"label": "Instagram", "accent": "#F43F5E"},
    "twitter": {"label": "X / Twitter", "accent": "#60A5FA"},
    "telegram": {"label": "Telegram", "accent": "#38BDF8"},
}

SOCIAL_FIELD_DEFINITIONS: dict[str, list[dict[str, Any]]] = {
    "whatsapp": [
        {"key": "phone_number_id", "label": "Phone number ID", "required": True, "secret": False},
        {"key": "access_token", "label": "Cloud API access token", "required": True, "secret": True},
        {"key": "webhook_verify_token", "label": "Webhook verify token", "required": False, "secret": True, "advanced": True, "auto": True},
        {"key": "business_account_id", "label": "Business account ID", "required": False, "secret": False, "advanced": True},
    ],
    "instagram": [
        {"key": "page_access_token", "label": "Page access token", "required": True, "secret": True},
        {"key": "instagram_business_account_id", "label": "Instagram business account ID", "required": True, "secret": False},
        {"key": "webhook_verify_token", "label": "Webhook verify token", "required": False, "secret": True, "advanced": True, "auto": True},
        {"key": "app_secret", "label": "App secret", "required": False, "secret": True, "advanced": True},
    ],
    "twitter": [
        {"key": "bearer_token", "label": "Bearer token", "required": True, "secret": True},
        {"key": "api_key", "label": "API key", "required": False, "secret": True, "advanced": True},
        {"key": "api_secret", "label": "API secret", "required": False, "secret": True, "advanced": True},
        {"key": "access_token", "label": "Access token", "required": False, "secret": True, "advanced": True},
        {"key": "access_token_secret", "label": "Access token secret", "required": False, "secret": True, "advanced": True},
    ],
    "telegram": [
        {"key": "bot_token", "label": "Bot token", "required": True, "secret": True},
        {"key": "default_chat_id", "label": "Default chat ID", "required": False, "secret": False, "advanced": True},
        {"key": "webhook_secret", "label": "Webhook secret", "required": False, "secret": True, "advanced": True, "auto": True},
    ],
}

SOCIAL_REQUIRED_FIELDS: dict[str, list[str]] = {
    platform: [field["key"] for field in fields if field.get("required")]
    for platform, fields in SOCIAL_FIELD_DEFINITIONS.items()
}

BROWSER_AUTOMATION_PROVIDER = "browser-automation"
BROWSER_AUTOMATION_DEFAULTS: dict[str, bool] = {
    "open_links": True,
    "open_close_tabs": True,
    "type_into_page": True,
    "edit_fields": True,
    "delete_draft_content": True,
    "background_open": True,
}
BROWSER_AUTOMATION_ACTIONS: list[dict[str, str]] = [
    {
        "key": "open_url",
        "label": "Open link",
        "permission": "open_links",
        "description": "Open any URL in the default browser.",
    },
    {
        "key": "open_youtube_song",
        "label": "Open YouTube search",
        "permission": "open_links",
        "description": "Open a YouTube search for a song or playlist in the default browser.",
    },
    {
        "key": "new_tab",
        "label": "Open tab",
        "permission": "open_close_tabs",
        "description": "Create a new tab in the active browser window.",
    },
    {
        "key": "close_tab",
        "label": "Close tab",
        "permission": "open_close_tabs",
        "description": "Close the current active browser tab.",
    },
    {
        "key": "type_text",
        "label": "Type into page",
        "permission": "type_into_page",
        "description": "Type text into the currently focused browser field.",
    },
    {
        "key": "edit_field",
        "label": "Edit field",
        "permission": "edit_fields",
        "description": "Replace the content of the focused field.",
    },
    {
        "key": "remove_draft",
        "label": "Clear draft",
        "permission": "delete_draft_content",
        "description": "Select and delete the current draft or focused field content.",
    },
    {
        "key": "open_app",
        "label": "Open desktop app",
        "permission": "open_links",
        "description": "Open a desktop app such as Notepad, Calculator, Explorer, VS Code, or Chrome.",
    },
    {
        "key": "close_window",
        "label": "Close desktop window",
        "permission": "open_close_tabs",
        "description": "Close the currently active desktop app window.",
    },
    {
        "key": "switch_window",
        "label": "Switch desktop window",
        "permission": "open_close_tabs",
        "description": "Move to the next open desktop app window.",
    },
    {
        "key": "volume_up",
        "label": "Increase volume",
        "permission": "open_links",
        "description": "Raise Windows system volume.",
    },
    {
        "key": "volume_down",
        "label": "Decrease volume",
        "permission": "open_links",
        "description": "Lower Windows system volume.",
    },
    {
        "key": "brightness_up",
        "label": "Increase brightness",
        "permission": "open_links",
        "description": "Raise Windows screen brightness when the display supports WMI brightness control.",
    },
    {
        "key": "brightness_down",
        "label": "Decrease brightness",
        "permission": "open_links",
        "description": "Lower Windows screen brightness when the display supports WMI brightness control.",
    },
]

DESKTOP_APP_ALIASES: dict[str, list[str]] = {
    "notepad": ["notepad", "notepad app", "notepad desktop", "notepad desktop app"],
    "calculator": ["calculator", "calc"],
    "file explorer": ["file explorer", "explorer"],
    "vscode": ["vscode", "vs code", "visual studio code", "code editor"],
    "chrome": [
        "chrome",
        "google chrome",
        "chrome browser",
        "google chrome browser",
        "chrome app",
        "google chrome app",
        "chrome desktop",
        "google chrome desktop",
    ],
    "brave": [
        "brave",
        "brave browser",
        "brave app",
        "brave desktop",
    ],
    "edge": [
        "edge",
        "microsoftedge",
        "microsoft edge",
        "edge browser",
        "microsoft edge browser",
        "edge app",
        "microsoft edge app",
        "edge desktop",
        "microsoft edge desktop",
    ],
    "command prompt": ["command prompt", "cmd"],
    "powershell": ["powershell"],
    "whatsapp": [
        "whatsapp",
        "whats app",
        "whatsup",
        "watsup",
        "whatsap",
        "whatsapp desktop",
        "whats app desktop",
        "whatsup desktop",
        "whatsapp app",
        "whatsapp desktop app",
    ],
    "telegram": ["telegram", "telegram app", "telegram desktop", "telegram desktop app"],
    "discord": ["discord", "discord app", "discord desktop", "discord desktop app"],
    "word": ["word", "microsoft word", "ms word"],
    "excel": ["excel", "microsoft excel", "ms excel"],
    "powerpoint": ["powerpoint", "power point", "microsoft powerpoint", "ms powerpoint"],
    "settings": ["settings", "windows settings"],
    "terminal": ["terminal", "windows terminal"],
    "control panel": ["control panel"],
}

DUAL_MODE_APP_TARGETS: dict[str, dict[str, str | None]] = {
    "whatsapp": {
        "label": "WhatsApp",
        "desktop_app": "whatsapp",
        "web_url": "https://web.whatsapp.com",
    },
    "telegram": {
        "label": "Telegram",
        "desktop_app": "telegram",
        "web_url": "https://web.telegram.org",
    },
    "discord": {
        "label": "Discord",
        "desktop_app": "discord",
        "web_url": "https://discord.com/app",
    },
    "instagram": {
        "label": "Instagram",
        "desktop_app": None,
        "web_url": "https://www.instagram.com",
    },
    "twitter": {
        "label": "X / Twitter",
        "desktop_app": None,
        "web_url": "https://x.com",
    },
}

DESKTOP_ONLY_APP_TARGETS: set[str] = {
    "notepad",
    "calculator",
    "file explorer",
    "vscode",
    "command prompt",
    "powershell",
    "word",
    "excel",
    "powerpoint",
    "settings",
    "terminal",
    "control panel",
}

BROWSER_APP_LABELS: dict[str, str] = {
    "chrome": "Google Chrome",
    "brave": "Brave",
    "edge": "Microsoft Edge",
}

SPECIAL_FOLDERS: dict[str, str] = {
    "downloads": str((Path.home() / "Downloads")),
    "desktop": str((Path.home() / "Desktop")),
    "documents": str((Path.home() / "Documents")),
    "pictures": str((Path.home() / "Pictures")),
    "videos": str((Path.home() / "Videos")),
    "music": str((Path.home() / "Music")),
}

KNOWN_LOGIN_URLS: dict[str, dict[str, Any]] = {
    "codechef.com": {
        "url": "https://www.codechef.com/login?page=1",
        "prefill_delay": 3.0,
        "tab_presses_before": 1,
        "type_interval": 0.07,
        "step_delay": 0.18,
    },
    "linkedin.com": {
        "url": "https://www.linkedin.com/login",
        "prefill_delay": 2.4,
        "tab_presses_before": 0,
        "type_interval": 0.06,
        "step_delay": 0.14,
    },
    "instagram.com": {
        "url": "https://www.instagram.com/accounts/login/",
        "prefill_delay": 2.8,
        "tab_presses_before": 0,
        "type_interval": 0.06,
        "step_delay": 0.14,
    },
    "twitter.com": {
        "url": "https://x.com/i/flow/login",
        "prefill_delay": 2.8,
        "tab_presses_before": 0,
        "type_interval": 0.06,
        "step_delay": 0.14,
    },
    "x.com": {
        "url": "https://x.com/i/flow/login",
        "prefill_delay": 2.8,
        "tab_presses_before": 0,
        "type_interval": 0.06,
        "step_delay": 0.14,
    },
    "github.com": {
        "url": "https://github.com/login",
        "prefill_delay": 2.2,
        "tab_presses_before": 0,
        "type_interval": 0.05,
        "step_delay": 0.12,
    },
    "leetcode.com": {
        "url": "https://leetcode.com/accounts/login/",
        "prefill_delay": 2.6,
        "tab_presses_before": 0,
        "type_interval": 0.05,
        "step_delay": 0.12,
    },
    "codeforces.com": {
        "url": "https://codeforces.com/enter",
        "prefill_delay": 2.6,
        "tab_presses_before": 0,
        "type_interval": 0.05,
        "step_delay": 0.12,
    },
}

AUTOMATION_OPENABLE_TARGETS = (
    "notepad|calculator|calc|file explorer|explorer|vscode|visual studio code|chrome|brave|edge|"
    "microsoft edge|whatsapp|telegram|discord|word|excel|powerpoint|settings|terminal|control panel|"
    "youtube|google|codechef|linkedin|instagram|twitter|x"
)


def normalize_browser_automation_prompt(prompt: str) -> str:
    normalized = " ".join(prompt.split())
    desktop_slash = re.match(r"^/desktop\s+(.+)$", normalized, flags=re.IGNORECASE)
    if desktop_slash:
        target = re.sub(r"^\s*open\s+", "", desktop_slash.group(1), flags=re.IGNORECASE).strip()
        normalized = f"open {target} in the desktop app"

    website_slash = re.match(r"^/(?:web|website)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if website_slash:
        target = re.sub(r"^\s*open\s+", "", website_slash.group(1), flags=re.IGNORECASE).strip()
        normalized = f"open {target} in the web browser"

    desktop_prefix = re.match(r"^(?:desktop|desktop app|desktop application)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if desktop_prefix:
        target = re.sub(r"^\s*open\s+", "", desktop_prefix.group(1), flags=re.IGNORECASE).strip()
        normalized = f"open {target} in the desktop app"

    website_prefix = re.match(r"^(?:web|website|browser)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if website_prefix:
        target = re.sub(r"^\s*open\s+", "", website_prefix.group(1), flags=re.IGNORECASE).strip()
        normalized = f"open {target} in the web browser"

    normalized = re.sub(r"\bweb\s+site\b", "website", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwebsite version\b", "website", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bweb version\b", "website", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bdesktop version\b", "desktop app", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bdesktop client\b", "desktop app", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bweb client\b", "website", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bin\s+website\b", "in the web browser", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bon\s+website\b", "in the web browser", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bin\s+web\b", "in the web browser", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bin\s+desktop\b", "in the desktop app", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwhats?\s*up\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwats?\s*up\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwhats?\s*ap+p?\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwhats\s+app\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwhastapp\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmicrosoftedge\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmicro\s*soft edge\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bms edge\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bedge browser\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmicrosoft edge browser\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bedge app\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmicrosoft edge app\b", "microsoft edge", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bchrome browser\b", "google chrome", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bchrome app\b", "google chrome", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bgoogle chrome app\b", "google chrome", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        rf"\bop(?:en)?\s*({AUTOMATION_OPENABLE_TARGETS})\b",
        r"open \1",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\bdesktop\s+open\b", "open", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\byoutub\b", "youtube", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bcaland(ar|er)?\b", "calendar", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def extract_first_url_or_domain(prompt: str) -> str | None:
    url_match = re.search(r"(https?://[^\s]+)", prompt, flags=re.IGNORECASE)
    if url_match:
        return url_match.group(1).rstrip(".,)")

    domain_match = re.search(
        r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|org|net|io|ai|co|app|dev))\b",
        prompt,
        flags=re.IGNORECASE,
    )
    if domain_match:
        return domain_match.group(1)
    return None


def extract_search_phrase(prompt: str) -> str | None:
    quoted = re.search(r'"([^"]+)"|\'([^\']+)\'', prompt)
    if quoted:
        return next(group for group in quoted.groups() if group)

    for marker in ["search for", "look for", "find", "play", "search"]:
        match = re.search(rf"{marker}\s+(.+)", prompt, flags=re.IGNORECASE)
        if match:
            phrase = re.split(r"\b(?:on|in|using|at)\b", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
            return phrase.strip(" .")
    return None


def extract_field_value(prompt: str, field_names: list[str]) -> str | None:
    for field in field_names:
        pattern = rf"\b{re.escape(field)}\b\s*(?:is|=|:)?\s*([^\n,;]+)"
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("\"'")
    return None


def extract_login_credentials(prompt: str) -> tuple[str | None, str | None]:
    username_match = re.search(
        r"\b(?:username|user\s*id|login\s*id|email)\b\s*[-:=]?\s*(.+?)(?=\s+\b(?:password|passcode)\b|$)",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    password_match = re.search(
        r"\b(?:password|passcode)\b\s*[-:=]?\s*(.+?)(?=$)",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )

    username = username_match.group(1).strip().strip("\"'") if username_match else None
    password = password_match.group(1).strip().strip("\"'") if password_match else None
    return username, password


def normalize_domain(url_or_domain: str | None) -> str | None:
    if not url_or_domain:
        return None
    normalized = url_or_domain.lower().strip()
    normalized = re.sub(r"^https?://", "", normalized)
    normalized = normalized.split("/")[0]
    return normalized


def detect_known_site(prompt: str) -> str | None:
    lowered = prompt.lower()
    if re.search(r"\bgoogle\b", lowered) and not re.search(r"\bgoogle chrome\b", lowered):
        return "google.com"
    if "codechef" in lowered:
        return "codechef.com"
    if "linkedin" in lowered:
        return "linkedin.com"
    if "instagram" in lowered:
        return "instagram.com"
    if "youtube" in lowered:
        return "youtube.com"
    if "codeforces" in lowered:
        return "codeforces.com"
    if "leetcode" in lowered:
        return "leetcode.com"
    if "github" in lowered:
        return "github.com"
    return None


def humanize_desktop_target(app_name: str | None) -> str:
    if not app_name:
        return "the requested app"
    friendly_names = {
        "notepad": "Notepad",
        "calculator": "Calculator",
        "file explorer": "File Explorer",
        "vscode": "Visual Studio Code",
        "command prompt": "Command Prompt",
        "powershell": "PowerShell",
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "discord": "Discord",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "settings": "Windows Settings",
        "terminal": "Windows Terminal",
        "control panel": "Control Panel",
        "chrome": "Google Chrome",
        "brave": "Brave",
        "edge": "Microsoft Edge",
    }
    return friendly_names.get(app_name, app_name.title())


def detect_desktop_app(prompt: str) -> str | None:
    lowered = prompt.lower()
    for app_name, aliases in DESKTOP_APP_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases):
            return app_name
    return None


def detect_dual_mode_app(prompt: str) -> str | None:
    lowered = prompt.lower()
    if re.search(r"\b(?:whats\s*app|whatsup|watsup|whatsap)\b", lowered):
        return "whatsapp"
    if re.search(r"\btelegram\b", lowered):
        return "telegram"
    if re.search(r"\bdiscord\b", lowered):
        return "discord"
    if re.search(r"\binstagram\b", lowered):
        return "instagram"
    if re.search(r"\b(?:twitter|x)\b", lowered):
        return "twitter"
    return None


def has_desktop_app_context(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(desktop|desktop app|desktop application|desktop mode|desktop only|desktop version|windows app|installed app|local app|native app|pc app|desktop client|desktop software|desktop program|open the app|open on desktop|on desktop|in the desktop|on my laptop|on my pc|in desktop|desktop side)\b",
            prompt,
            flags=re.IGNORECASE,
        )
    )


def has_web_app_context(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(web|web app|website|website mode|website only|browser|browser version|site|online|tab|web version|website version|open in chrome|open in brave|open in edge|in the browser|open on the website|on the website|web page|web side)\b",
            prompt,
            flags=re.IGNORECASE,
        )
    )


def has_explicit_website_context(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(website|web\s*site|site|online|web app|web version|website version|web browser|browser version|in the browser|on the web|website only|web side|browser side)\b",
            prompt,
            flags=re.IGNORECASE,
        )
    )


def extract_generic_desktop_app_request(prompt: str) -> str | None:
    patterns = [
        r"\bdesktop\s+(?:open|launch|start|use)\s+(.+?)(?:\s+app)?\b",
        r"\bdesktop\s+app\s+(?:open|launch|start|use)\s+(.+?)(?:\s+app)?\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+in\s+the\s+desktop\s+app\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+in\s+desktop\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+as\s+the\s+desktop\s+app\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+desktop\s+app\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+desktop\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" .\"'")
            if candidate:
                return candidate
    return None


def extract_generic_website_request(prompt: str) -> str | None:
    patterns = [
        r"\b(?:website|web|browser)\s+(?:open|launch|start|use)\s+(.+)\b",
        r"\b(?:website|web|browser|site)\s+(?:open|launch|start|use)\s+(.+)\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+in\s+the\s+web(?:\s+browser)?\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+in\s+the\s+website\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+on\s+the\s+website\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+website\s+only\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+website\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+web\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" .\"'")
            if candidate:
                return candidate
    return None


def _clean_contact_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().strip("\"'").strip(" .,:;")
    cleaned = re.sub(r"^(?:the\s+contact\s+|contact\s+|chat\s+with\s+|to\s+)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:on|in|through|via)\s+whatsapp(?:\s+desktop|\s+app|\s+website|\s+web)?\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bwhatsapp(?:\s+desktop|\s+app|\s+website|\s+web)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:desktop|website|web)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.split(
        r"\b(?:case\s+sensitive|case\s+sensitivity|ignore\s+case|no\s+worries|spelling\s+mistake|spelling\s+mistakes|typo|typos)\b",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    normalized_lower = cleaned.lower()
    relationship_aliases = {
        "mumy": "mummy",
        "mummi": "mummy",
        "mummie": "mummy",
        "mumyy": "mummy",
        "mommy": "mummy",
        "mom": "mummy",
        "mother": "mummy",
        "ammah": "amma",
        "ammaa": "amma",
        "ammah": "amma",
        "dad": "daddy",
        "dady": "daddy",
        "dadddy": "daddy",
        "father": "daddy",
        "pappa": "papa",
        "nannaa": "nanna",
    }
    cleaned = relationship_aliases.get(normalized_lower, cleaned)
    return cleaned or None


def _normalize_whatsapp_allowed_contact(contact: str | None) -> str | None:
    if not contact:
        return None

    normalized = contact.lower()
    normalized = re.sub(
        r"\b(?:on|in|through|via)\s+(?:the\s+)?(?:whatsapp\s+)?(?:desktop|desktop app|app|website|web|web browser|browser)\b",
        "",
        normalized,
    )
    normalized = re.sub(r"\b(?:whatsapp|desktop|app|website|web|browser)\b", "", normalized)
    normalized = re.sub(r"[^a-z\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    allowed_aliases = {
        "amma": "Amma",
        "ammaa": "Amma",
        "ammah": "Amma",
        "amm": "Amma",
        "am ma": "Amma",
        "mummy": "Amma",
        "mumyy": "Amma",
        "mommy": "Amma",
        "mom": "Amma",
        "mother": "Amma",
        "mamma": "Amma",
        "mumy": "Amma",
    }
    return allowed_aliases.get(normalized)


def _whatsapp_safety_clarification(contact: str | None) -> dict[str, Any] | None:
    if not contact:
        return None

    allowed_contact = _normalize_whatsapp_allowed_contact(contact)
    if allowed_contact:
        return None

    return {
        "summary": (
            "For safety, WhatsApp message automation is limited to the Amma contact in this build. "
            "I will not open or send to another WhatsApp chat from automation."
        ),
        "steps": [],
        "needs_clarification": True,
    }


def _clean_message_body(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().strip("\"'")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or None


def _strip_schedule_phrases(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value
    schedule_patterns = [
        r"\b(?:today|tomorrow)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
        r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:today|tomorrow)?\b",
        r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:today|tomorrow)?\b",
    ]
    for pattern in schedule_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:with|and)\s+(?:a\s+)?remind(?:er| me)\b", "", cleaned, flags=re.IGNORECASE)
    return _clean_message_body(cleaned)


def extract_prompt_schedule(prompt: str) -> tuple[str | None, str]:
    lowered = prompt.lower()
    now = datetime.now().astimezone()
    run_at: datetime | None = None

    match = re.search(
        r"\b(?:(today|tomorrow)\s+)?(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        lowered,
        flags=re.IGNORECASE,
    )
    if match:
        day_hint, hour_text, minute_text, period = match.groups()
        hour = int(hour_text)
        minute = int(minute_text or "0")
        if hour == 12:
            hour = 0
        if period.lower() == "pm":
            hour += 12
        target_date = now.date()
        if day_hint == "tomorrow":
            target_date = target_date + timedelta(days=1)
        candidate = datetime.combine(target_date, datetime.min.time(), tzinfo=now.tzinfo).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if day_hint != "tomorrow" and candidate <= now:
            candidate = candidate + timedelta(days=1)
        run_at = candidate
        prompt = re.sub(match.group(0), "", prompt, flags=re.IGNORECASE).strip()
        prompt = re.sub(r"\s{2,}", " ", prompt)

    return run_at.isoformat() if run_at else None, prompt


def extract_send_message_details(prompt: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"\s+", " ", prompt.strip())
    normalized = re.sub(r"\bwhats?\s*up\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwats?\s*up\b", "whatsapp", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bwhats?\s*ap+p?\b", "whatsapp", normalized, flags=re.IGNORECASE)

    explicit_message_patterns: list[tuple[str, str, str]] = [
        (
            r"\bopen\s+whatsapp(?:\s+desktop|\s+app)?\s+and\s+send\s+(?P<message>.+?)\s+(?:message\s+)?to\s+(?P<contact>[^,.;\n]+)",
            "message",
            "contact",
        ),
        (
            r"\bsend\s+(?P<message>.+?)\s+message\s+to\s+(?P<contact>[^,.;\n]+)",
            "message",
            "contact",
        ),
        (
            r"\bsend\s+(?P<message>.+?)\s+to\s+(?P<contact>[^,.;\n]+)",
            "message",
            "contact",
        ),
        (
            r"\bmessage\s+(?P<contact>[^,.;\n]+?)\s+(?:saying|with|message|text)\s+(?P<message>.+)",
            "message",
            "contact",
        ),
        (
            r"\bsend\s+to\s+(?P<contact>[^,.;\n]+?)\s+(?:saying|with|message|text)\s+(?P<message>.+)",
            "message",
            "contact",
        ),
        (
            r"\bsend\s+(?:a\s+message\s+)?to\s+(?P<contact>[^,.;\n]+?)\s+(?:saying|with|message|text)\s+(?P<message>.+)",
            "message",
            "contact",
        ),
    ]

    for pattern, message_key, contact_key in explicit_message_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        message = _strip_schedule_phrases(match.group(message_key))
        contact = _clean_contact_name(_strip_schedule_phrases(match.group(contact_key)))
        if message and message.lower() in {"a", "message", "the message"} and contact:
            return None, contact
        if message and contact:
            return message, contact

    contact_only_patterns = [
        r"\bsend\s+(?:a\s+message|message)\s+to\s+(?P<contact>[^,;\n]+?)(?:[.?!]?)$",
        r"\bopen\s+whatsapp(?:\s+desktop|\s+app)?\s+and\s+send\s+(?:a\s+message|message)\s+to\s+(?P<contact>[^,;\n]+?)(?:[.?!]?)$",
        r"\bopen\s+whatsapp(?:\s+desktop|\s+app)?\s+and\s+send\s+(?P<contact>[^,;\n]+?)(?:[.?!]?)$",
        r"\bopen\s+whatsapp(?:\s+desktop|\s+app)?\s+and\s+message\s+(?P<contact>[^,;\n]+?)(?:[.?!]?)$",
    ]
    for pattern in contact_only_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            contact = _clean_contact_name(match.group("contact"))
            if contact:
                return None, contact

    patterns: list[tuple[str, str, str]] = [
        (
            r"\bsend\s+(?P<message>.+?)\s+(?:message\s+)?to\s+(?P<contact>[^,.;\n]+)",
            "message",
            "contact",
        ),
    ]

    for pattern, message_key, contact_key in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        message = _strip_schedule_phrases(match.group(message_key))
        contact = _clean_contact_name(_strip_schedule_phrases(match.group(contact_key)))
        if message and message.lower() in {"a", "message", "the message"} and contact:
            return None, contact
        if message or contact:
            return message, contact

    contact_only_match = re.search(
        r"\b(?:send|message)\s+(?:a\s+message\s+)?to\s+(?P<contact>[^,.;\n]+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if contact_only_match:
        return None, _clean_contact_name(_strip_schedule_phrases(contact_only_match.group("contact")))

    open_and_send_match = re.search(
        r"\bopen\s+(?:the\s+)?whatsapp(?:\s+desktop|\s+app)?\s+and\s+send\s+(?P<message>.+?)\s+to\s+(?P<contact>[^,.;\n]+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if open_and_send_match:
        return (
            _strip_schedule_phrases(open_and_send_match.group("message")),
            _clean_contact_name(_strip_schedule_phrases(open_and_send_match.group("contact"))),
        )

    return None, None


def extract_open_target(prompt: str) -> str | None:
    patterns = [
        r"\b(?:open|launch|start|use)\s+(.+?)\s+(?:in|on)\s+the\s+(?:desktop app|desktop|web browser|browser|website)\b",
        r"\b(?:open|launch|start|use)\s+(.+?)\s+(?:desktop app|desktop|website|web browser|browser)\b",
        r"\b(?:open|launch|start|use)\s+(.+?)(?:\s+and\s+.+)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip(" .\"'")
        if candidate:
            candidate = re.sub(r"\b(the|my)\b", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s+", " ", candidate).strip()
            if candidate:
                return candidate
    return None


def extract_windows_path(prompt: str) -> str | None:
    match = re.search(r"([A-Za-z]:\\[^\n\r\"']+)", prompt)
    if match:
        return match.group(1).strip()
    return None


def detect_special_folder(prompt: str) -> str | None:
    lowered = prompt.lower()
    for key in SPECIAL_FOLDERS.keys():
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            return key
    return None


def extract_create_folder_name(prompt: str) -> str | None:
    match = re.search(
        r"(?:create|make)\s+(?:another\s+|a\s+new\s+)?folder(?:\s+named|\s+called|\s+with\s+name)?\s+([^\n,.;]+)",
        prompt,
        flags=re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip().strip('"')
        if name.lower() not in {"in", "same", "the same"}:
            return name
    return None


def extract_run_command(prompt: str) -> tuple[str | None, str]:
    powershell_match = re.search(r"(?:run|execute)\s+(?:powershell|pwsh)\s+command\s+(.+)", prompt, flags=re.IGNORECASE)
    if powershell_match:
        return powershell_match.group(1).strip(), "powershell"

    cmd_match = re.search(r"(?:run|execute)\s+cmd\s+command\s+(.+)", prompt, flags=re.IGNORECASE)
    if cmd_match:
        return cmd_match.group(1).strip(), "cmd"

    generic_match = re.search(r"(?:run|execute)\s+command\s+(.+)", prompt, flags=re.IGNORECASE)
    if generic_match:
        return generic_match.group(1).strip(), "powershell"

    return None, "powershell"


def is_complex_site_workflow(prompt: str) -> bool:
    lowered = prompt.lower()
    workflow_tokens = [
        "complete all",
        "solve all",
        "submit all",
        "verify if",
        "go to another question",
        "complete the path",
        "difficulty",
        "section",
        "pop up a message",
        "do the corrections",
    ]
    return any(token in lowered for token in workflow_tokens)


def build_browser_prompt_plan(prompt: str) -> dict[str, Any]:
    normalized = normalize_browser_automation_prompt(prompt)
    lowered = normalized.lower()
    url_or_domain = extract_first_url_or_domain(normalized)
    normalized_domain = normalize_domain(url_or_domain) or detect_known_site(normalized)
    windows_path = extract_windows_path(normalized)
    special_folder = detect_special_folder(normalized)
    search_phrase = extract_search_phrase(normalized)
    username_value, password_value = extract_login_credentials(normalized)
    email_value = username_value or extract_field_value(normalized, ["email", "username", "user id", "login id"])
    message_value = extract_field_value(normalized, ["message", "text", "reply"])
    desktop_app = detect_desktop_app(normalized)
    requested_desktop_app = extract_generic_desktop_app_request(normalized)
    requested_website_target = extract_generic_website_request(normalized)
    dual_mode_app = detect_dual_mode_app(normalized)
    desktop_context = has_desktop_app_context(normalized)
    web_context = has_web_app_context(normalized)
    explicit_website_context = has_explicit_website_context(normalized)
    dual_mode_native_app_hint = bool(
        dual_mode_app
        and re.search(
            rf"\b(?:{re.escape(dual_mode_app)}|{re.escape(str(DUAL_MODE_APP_TARGETS.get(dual_mode_app, {}).get('label', dual_mode_app)))})\s+app\b",
            lowered,
            flags=re.IGNORECASE,
        )
    )
    if dual_mode_native_app_hint and not explicit_website_context:
        desktop_context = True
    browser_app = desktop_app if desktop_app in BROWSER_APP_LABELS else None
    is_open_request = any(token in lowered for token in ["open", "launch", "start", "use"])
    created_folder_name = extract_create_folder_name(normalized) or "Converted_PPTs"
    shell_command, shell_name = extract_run_command(normalized)
    send_message_text, send_message_contact = extract_send_message_details(normalized)
    if send_message_contact and (dual_mode_app == "whatsapp" or desktop_app == "whatsapp" or "whatsapp" in lowered):
        whatsapp_safety_response = _whatsapp_safety_clarification(send_message_contact)
        if whatsapp_safety_response:
            return whatsapp_safety_response
        send_message_contact = _normalize_whatsapp_allowed_contact(send_message_contact) or send_message_contact
    requested_open_target = extract_open_target(normalized)
    typed_match = re.search(r"\b(?:type|write|send)\b\s+(.+)", normalized, flags=re.IGNORECASE)
    typed_instruction = None
    if typed_match:
        typed_instruction = re.split(
            r"\b(?:to the active field|in the active field|into the active field|to the field|in the field|into the field)\b",
            typed_match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .")

    steps: list[dict[str, Any]] = []
    summary = "Prepared a browser automation plan."

    if any(token in lowered for token in ["close tab", "remove tab"]):
        steps.append({"action": "close_tab"})
        summary = "Closing the current browser tab."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["new tab", "open tab"]):
        steps.append({"action": "new_tab"})
        summary = "Opening a new browser tab."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["clear draft", "delete draft", "remove draft", "clear field"]):
        steps.append({"action": "remove_draft"})
        summary = "Clearing the active draft or field."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["volume", "sound", "audio"]):
        amount_match = re.search(r"\b(?:by|to)\s+(\d{1,3})\b", lowered)
        amount = int(amount_match.group(1)) if amount_match else 5
        if any(token in lowered for token in ["mute", "silent", "silence"]):
            steps.append({"action": "volume_mute"})
            summary = "Toggling system mute."
            return {"summary": summary, "steps": steps}
        if any(token in lowered for token in ["increase", "raise", "up", "higher", "louder"]):
            steps.append({"action": "volume_up", "payload": {"amount": amount}})
            summary = "Increasing system volume."
            return {"summary": summary, "steps": steps}
        if any(token in lowered for token in ["decrease", "reduce", "lower", "down", "quieter"]):
            steps.append({"action": "volume_down", "payload": {"amount": amount}})
            summary = "Decreasing system volume."
            return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["brightness", "screen light", "display light"]):
        amount_match = re.search(r"\b(?:by|to|at)\s+(\d{1,3})\s*%?\b", lowered)
        amount = int(amount_match.group(1)) if amount_match else 10
        if any(token in lowered for token in ["set", "make", "to ", "at "]):
            steps.append({"action": "set_brightness", "payload": {"amount": amount}})
            summary = f"Setting screen brightness to {amount}%."
            return {"summary": summary, "steps": steps}
        if any(token in lowered for token in ["increase", "raise", "up", "higher", "brighter"]):
            steps.append({"action": "brightness_up", "payload": {"amount": amount}})
            summary = "Increasing screen brightness."
            return {"summary": summary, "steps": steps}
        if any(token in lowered for token in ["decrease", "reduce", "lower", "down", "dim"]):
            steps.append({"action": "brightness_down", "payload": {"amount": amount}})
            summary = "Decreasing screen brightness."
            return {"summary": summary, "steps": steps}

    if "play" in lowered and any(token in lowered for token in ["song", "songs", "music", "movie", "movies"]):
        query = search_phrase or re.sub(
            r"\b(open|youtube|play|please|song|songs|music|movie|movies)\b",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        query = " ".join(query.split()).strip(" .") or normalized
        steps.append({"action": "open_youtube_song", "target": query})
        summary = f"Opening YouTube and searching for {query}."
        return {"summary": summary, "steps": steps}

    if normalized_domain == "codechef.com" and any(token in lowered for token in ["practice", "problem section", "practice problem"]):
        java_path = "https://www.codechef.com/practice/java" if "java" in lowered else "https://www.codechef.com/practice"
        steps.append({"action": "open_url", "target": java_path})

        if is_complex_site_workflow(normalized):
            steps.append(
                {
                    "action": "unsupported_browser_workflow",
                    "payload": {
                        "message": (
                            "I opened the CodeChef practice path, but this kind of multi-step site workflow "
                            "needs a DOM-aware web agent. The current automation will not auto-solve or submit "
                            "CodeChef practice problems."
                        ),
                        "note": (
                            "This prevents the old behavior where the full prompt was typed into random text boxes."
                        ),
                    },
                }
            )
            summary = "Opening the CodeChef practice path without dumping your prompt into the page."
            return {"summary": summary, "steps": steps}

        summary = "Opening the CodeChef practice path."
        return {"summary": summary, "steps": steps}

    if shell_command:
        steps.append({"action": "run_command", "target": shell_command, "payload": {"shell": shell_name}})
        summary = f"Running the requested {shell_name} command."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["convert all pdfs to ppts", "convert pdfs to ppts", "convert pdf to ppt", "convert pdfs to pptx"]):
        source_path = windows_path or SPECIAL_FOLDERS.get(special_folder or "", SPECIAL_FOLDERS["downloads"])
        steps.append(
            {
                "action": "convert_pdfs_to_ppts",
                "payload": {
                    "source_path": source_path,
                    "output_folder_name": created_folder_name,
                },
            }
        )
        summary = f"Converting all PDFs in {source_path} into PPTX files and placing them in {created_folder_name}."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["open folder", "open path", "go to files", "go to folder", "open downloads", "open desktop", "open documents"]):
        source_path = windows_path or SPECIAL_FOLDERS.get(special_folder or "", "")
        if source_path:
            steps.append({"action": "open_path", "payload": {"path": source_path}})
            summary = f"Opening {source_path} in File Explorer."
            return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["close window", "close app", "exit app"]):
        steps.append({"action": "close_window"})
        summary = "Closing the current desktop app window."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["switch window", "switch app", "change window"]):
        steps.append({"action": "switch_window"})
        summary = "Switching to the next open desktop window."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["minimize window", "minimize app"]):
        steps.append({"action": "minimize_window"})
        summary = "Minimizing the current desktop window."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["maximize window", "maximize app"]):
        steps.append({"action": "maximize_window"})
        summary = "Maximizing the current desktop window."
        return {"summary": summary, "steps": steps}

    if is_open_request and requested_website_target:
        requested_target_app = detect_desktop_app(requested_website_target)
        requested_target_dual_mode = detect_dual_mode_app(requested_website_target)
        requested_target_domain = normalize_domain(extract_first_url_or_domain(requested_website_target)) or detect_known_site(
            requested_website_target
        )

        if requested_target_app in DESKTOP_ONLY_APP_TARGETS:
            label = humanize_desktop_target(requested_target_app)
            return {
                "summary": (
                    f"{label} is a Windows desktop app, not a website. "
                    f"Say '/desktop open {requested_target_app}' or 'open {requested_target_app} desktop app'."
                ),
                "steps": [],
                "needs_clarification": True,
            }

        if requested_target_app in BROWSER_APP_LABELS:
            browser_label = BROWSER_APP_LABELS[requested_target_app]
            return {
                "summary": (
                    f"{browser_label} is a desktop browser app, not a website. "
                    f"Say '/desktop open {requested_target_app}' to launch the browser, or '/website open google.com' to open a real website."
                ),
                "steps": [],
                "needs_clarification": True,
            }

        if requested_target_dual_mode:
            dual_mode_config = DUAL_MODE_APP_TARGETS[requested_target_dual_mode]
            label = str(dual_mode_config["label"])
            web_target = str(dual_mode_config["web_url"])
            if requested_target_dual_mode == "whatsapp" and send_message_contact:
                return {
                    "summary": (
                        "WhatsApp message sending is only supported in the desktop app path in this build. "
                        "Say '/desktop open whatsapp' or 'open whatsapp desktop and send hi to Amma'."
                    ),
                    "steps": [],
                    "needs_clarification": True,
                }
            web_steps = [{"action": "open_url", "target": web_target}]
            web_summary = f"Opening {label} in the browser."
            if typed_instruction:
                web_steps.append({"action": "wait", "payload": {"seconds": 1.8}})
                web_steps.append({"action": "type_text", "target": typed_instruction})
                web_summary = f"Opening {label} in the browser and typing the requested text."
            elif message_value:
                web_steps.append({"action": "wait", "payload": {"seconds": 1.8}})
                web_steps.append({"action": "type_text", "target": message_value})
                web_summary = f"Opening {label} in the browser and typing the provided message."
            return {"summary": web_summary, "steps": web_steps}

        if requested_target_domain:
            target_url = extract_first_url_or_domain(requested_website_target) or f"https://{requested_target_domain}"
            steps.append({"action": "open_url", "target": target_url})
            summary = f"Opening {requested_target_domain} in the default browser."
            return {"summary": summary, "steps": steps}

    if is_open_request and requested_open_target and web_context and not normalized_domain:
        requested_target_app = detect_desktop_app(requested_open_target)
        requested_target_dual_mode = detect_dual_mode_app(requested_open_target)
        if requested_target_app in DESKTOP_ONLY_APP_TARGETS:
            label = humanize_desktop_target(requested_target_app)
            return {
                "summary": (
                    f"{label} is a Windows desktop app, not a website. "
                    f"Say '/desktop open {requested_target_app}' or 'open {requested_target_app} desktop app'."
                ),
                "steps": [],
                "needs_clarification": True,
            }
        if requested_target_app in BROWSER_APP_LABELS:
            browser_label = BROWSER_APP_LABELS[requested_target_app]
            return {
                "summary": (
                    f"{browser_label} is a browser application, not a normal website. "
                    f"Say '/desktop open {requested_target_app}' to launch the app, or '/website open google.com' for a real site."
                ),
                "steps": [],
                "needs_clarification": True,
            }
        if requested_target_dual_mode:
            label = str(DUAL_MODE_APP_TARGETS[requested_target_dual_mode]["label"])
            return {
                "summary": (
                    f"{label} can open either as the desktop app or on the web. "
                    f"Say '/desktop open {label}' or '/website open {label}' so I choose the right one."
                ),
                "steps": [],
                "needs_clarification": True,
            }

    if is_open_request and desktop_app in DESKTOP_ONLY_APP_TARGETS and web_context:
        label = humanize_desktop_target(desktop_app)
        return {
            "summary": (
                f"{label} is a Windows desktop app, not a website. "
                f"Say '/desktop open {desktop_app}' or 'open {desktop_app} desktop app'."
            ),
            "steps": [],
            "needs_clarification": True,
        }

    if is_open_request and browser_app and normalized_domain:
        browser_label = BROWSER_APP_LABELS[browser_app]
        target_url = url_or_domain or f"https://{normalized_domain}"
        steps.append({"action": "open_app_url", "target": browser_app, "payload": {"url": target_url}})
        summary = f"Opening {normalized_domain} in {browser_label}."
        return {"summary": summary, "steps": steps}

    if is_open_request and browser_app and explicit_website_context and not normalized_domain and not search_phrase:
        browser_label = BROWSER_APP_LABELS[browser_app]
        return {
            "summary": (
                f"{browser_label} is a desktop browser app, not a website. "
                f"Say '/desktop open {browser_app}' to launch the app, or '/website open google.com' for a real website. "
                f"You can also say 'open google in {browser_app}' to open a website inside that browser."
            ),
            "steps": [],
            "needs_clarification": True,
        }

    if is_open_request and browser_app and desktop_context and not normalized_domain:
        browser_label = BROWSER_APP_LABELS[browser_app]
        steps.append({"action": "open_app", "target": browser_app})
        summary = f"Opening {browser_label} as the desktop browser app."
        return {"summary": summary, "steps": steps}

    if is_open_request and browser_app and not normalized_domain and not web_context:
        browser_label = BROWSER_APP_LABELS[browser_app]
        steps.append({"action": "open_app", "target": browser_app})
        summary = f"Opening {browser_label} as the desktop browser app."
        return {"summary": summary, "steps": steps}

    if dual_mode_app and any(token in lowered for token in ["open", "launch", "start", "use"]):
        dual_mode_config = DUAL_MODE_APP_TARGETS[dual_mode_app]
        label = str(dual_mode_config["label"])
        desktop_target = dual_mode_config["desktop_app"]
        web_target = str(dual_mode_config["web_url"])

        if desktop_context and web_context:
            return {
                "summary": (
                    f"I can open {label} as the desktop app or in the browser, but your prompt mentions both. "
                    f"Please say either '/desktop open {label}' or '/website open {label}'."
                ),
                "steps": [],
                "needs_clarification": True,
            }

        if desktop_context:
            if desktop_target:
                desktop_steps = [{"action": "open_app", "target": desktop_target}]
                desktop_summary = f"Opening the {label} desktop app."
                if dual_mode_app == "whatsapp" and send_message_contact:
                    desktop_steps.append({"action": "wait", "payload": {"seconds": 2.2}})
                    desktop_steps.append(
                        {
                            "action": "whatsapp_send_message",
                            "payload": {
                                "contact": send_message_contact,
                                "message": send_message_text or "",
                            },
                        }
                    )
                    desktop_summary = (
                        f"Opening WhatsApp desktop and sending '{send_message_text}' to {send_message_contact}."
                        if send_message_text
                        else f"Opening WhatsApp desktop and focusing the chat for {send_message_contact}."
                    )
                    return {
                        "summary": desktop_summary,
                        "steps": desktop_steps,
                    }
                if typed_instruction:
                    desktop_steps.append({"action": "wait", "payload": {"seconds": 1.4}})
                    desktop_steps.append({"action": "type_text", "target": typed_instruction})
                    desktop_summary = f"Opening the {label} desktop app and typing the requested text."
                elif message_value:
                    desktop_steps.append({"action": "wait", "payload": {"seconds": 1.4}})
                    desktop_steps.append({"action": "type_text", "target": message_value})
                    desktop_summary = f"Opening the {label} desktop app and typing the provided message."
                return {
                    "summary": desktop_summary,
                    "steps": desktop_steps,
                }
            return {
                "summary": (
                    f"I can open {label} on the web, but this setup does not have a reliable desktop app target for it yet. "
                    f"Please say '/website open {label}' or tell me the exact installed desktop app name."
                ),
                "steps": [],
                "needs_clarification": True,
            }

        if web_context:
            web_steps = [{"action": "open_url", "target": web_target}]
            web_summary = f"Opening {label} in the browser."
            if typed_instruction:
                web_steps.append({"action": "wait", "payload": {"seconds": 1.8}})
                web_steps.append({"action": "type_text", "target": typed_instruction})
                web_summary = f"Opening {label} in the browser and typing the requested text."
            elif message_value:
                web_steps.append({"action": "wait", "payload": {"seconds": 1.8}})
                web_steps.append({"action": "type_text", "target": message_value})
                web_summary = f"Opening {label} in the browser and typing the provided message."
            return {
                "summary": web_summary,
                "steps": web_steps,
            }

        if not desktop_target:
            web_steps = [{"action": "open_url", "target": web_target}]
            web_summary = (
                f"Opening {label} in the browser because this setup has a web target for it but not a reliable desktop app target."
            )
            if typed_instruction:
                web_steps.append({"action": "wait", "payload": {"seconds": 1.8}})
                web_steps.append({"action": "type_text", "target": typed_instruction})
                web_summary = f"Opening {label} in the browser and typing the requested text."
            elif message_value:
                web_steps.append({"action": "wait", "payload": {"seconds": 1.8}})
                web_steps.append({"action": "type_text", "target": message_value})
                web_summary = f"Opening {label} in the browser and typing the provided message."
            return {
                "summary": web_summary,
                "steps": web_steps,
            }

        return {
            "summary": (
                f"I can open {label} as the desktop app or in the browser. "
                f"Please say '/desktop open {label}' or '/website open {label}'."
            ),
            "steps": [],
            "needs_clarification": True,
        }

    if (
        dual_mode_app == "whatsapp"
        and send_message_contact
        and any(token in lowered for token in ["send", "message", "text", "reply"])
    ):
        if web_context or explicit_website_context:
            return {
                "summary": (
                    "WhatsApp message sending is only supported in the desktop app path in this build. "
                    "Say '/desktop open whatsapp' or 'open whatsapp desktop and send hi to Amma'."
                ),
                "steps": [],
                "needs_clarification": True,
            }

        desktop_steps = [{"action": "open_app", "target": "whatsapp"}, {"action": "wait", "payload": {"seconds": 2.2}}]
        desktop_steps.append(
            {
                "action": "whatsapp_send_message",
                "payload": {
                    "contact": send_message_contact,
                    "message": send_message_text or "",
                },
            }
        )
        desktop_summary = (
            f"Opening WhatsApp desktop and sending '{send_message_text}' to {send_message_contact}."
            if send_message_text
            else f"Opening WhatsApp desktop and focusing the chat for {send_message_contact}."
        )
        return {"summary": desktop_summary, "steps": desktop_steps}

    if is_open_request and normalized_domain and not dual_mode_app and not browser_app:
        target_url = url_or_domain or f"https://{normalized_domain}"
        steps.append({"action": "open_url", "target": target_url})
        summary = f"Opening {normalized_domain} in the default browser."
        return {"summary": summary, "steps": steps}

    if desktop_app and any(token in lowered for token in ["open", "launch", "start"]):
        steps.append({"action": "open_app", "target": desktop_app})
        summary = f"Opening {humanize_desktop_target(desktop_app)} on the desktop."
        if desktop_app == "whatsapp" and send_message_contact:
            steps.append({"action": "wait", "payload": {"seconds": 2.2}})
            steps.append(
                {
                    "action": "whatsapp_send_message",
                    "payload": {
                        "contact": send_message_contact,
                        "message": send_message_text or "",
                    },
                }
            )
            summary = (
                f"Opening WhatsApp and sending '{send_message_text}' to {send_message_contact}."
                if send_message_text
                else f"Opening WhatsApp and focusing the chat for {send_message_contact}."
            )
            return {"summary": summary, "steps": steps}
        if typed_instruction:
            steps.append({"action": "wait", "payload": {"seconds": 1.4}})
            steps.append({"action": "type_text", "target": typed_instruction})
            summary = f"Opening {humanize_desktop_target(desktop_app)} and typing the requested text."
        elif message_value:
            steps.append({"action": "wait", "payload": {"seconds": 1.4}})
            steps.append({"action": "type_text", "target": message_value})
            summary = f"Opening {humanize_desktop_target(desktop_app)} and typing the provided message."
        elif desktop_app == "calculator":
            operation_match = re.search(r"(?:do|calculate|compute)\s+([0-9+\-*/().\s]+)", normalized, flags=re.IGNORECASE)
            if operation_match:
                expression = operation_match.group(1).replace(" ", "")
                steps.append({"action": "wait", "payload": {"seconds": 1.2}})
                steps.append({"action": "type_text", "target": expression})
                steps.append({"action": "wait", "payload": {"seconds": 0.4}})
                steps.append({"action": "type_text", "target": "="})
                summary = f"Opening calculator and entering {expression}."
        return {"summary": summary, "steps": steps}

    if requested_desktop_app and desktop_context and any(token in lowered for token in ["open", "launch", "start", "use"]):
        steps.append({"action": "open_app", "target": requested_desktop_app})
        summary = f"Opening {humanize_desktop_target(requested_desktop_app)} on the desktop."
        requested_desktop_dual_mode = detect_dual_mode_app(requested_desktop_app)
        if requested_desktop_dual_mode == "whatsapp" and send_message_contact:
            steps.append({"action": "wait", "payload": {"seconds": 2.2}})
            steps.append(
                {
                    "action": "whatsapp_send_message",
                    "payload": {
                        "contact": send_message_contact,
                        "message": send_message_text or "",
                    },
                }
            )
            summary = (
                f"Opening WhatsApp desktop and sending '{send_message_text}' to {send_message_contact}."
                if send_message_text
                else f"Opening WhatsApp desktop and focusing the chat for {send_message_contact}."
            )
            return {"summary": summary, "steps": steps}
        if typed_instruction:
            steps.append({"action": "wait", "payload": {"seconds": 1.4}})
            steps.append({"action": "type_text", "target": typed_instruction})
            summary = f"Opening {humanize_desktop_target(requested_desktop_app)} on the desktop and typing the requested text."
        elif message_value:
            steps.append({"action": "wait", "payload": {"seconds": 1.4}})
            steps.append({"action": "type_text", "target": message_value})
            summary = f"Opening {humanize_desktop_target(requested_desktop_app)} on the desktop and typing the provided message."
        return {"summary": summary, "steps": steps}

    if (any(token in lowered for token in ["login", "sign in", "log in"]) or ((email_value or password_value) and normalized_domain)) and normalized_domain:
        login_meta = KNOWN_LOGIN_URLS.get(normalized_domain)
        if login_meta:
            steps.append({"action": "open_url", "target": login_meta["url"]})
        else:
            steps.append({"action": "open_url", "target": url_or_domain})

        if email_value or password_value:
            steps.append({"action": "wait", "payload": {"seconds": (login_meta or {}).get("prefill_delay", 2.4)}})
            steps.append(
                {
                    "action": "type_sequence",
                    "payload": {
                        "values": [value for value in [email_value, password_value] if value],
                        "submit": True,
                        "tab_presses_before": (login_meta or {}).get("tab_presses_before", 0),
                        "type_interval": (login_meta or {}).get("type_interval", 0.05),
                        "step_delay": (login_meta or {}).get("step_delay", 0.12),
                        "clear_each": True,
                    },
                }
            )
            summary = f"Opening the login page for {normalized_domain} and filling the provided credentials."
            return {"summary": summary, "steps": steps}

    if "youtube" in lowered:
        query = search_phrase or normalized
        steps.append({"action": "open_youtube_song", "target": query})
        summary = f"Opening YouTube and searching for {query}."
        return {"summary": summary, "steps": steps}

    if search_phrase:
        if url_or_domain and "google" in (url_or_domain.lower() if url_or_domain else ""):
            target_url = f"https://www.google.com/search?q={urlencode({'q': search_phrase})[2:]}"
            steps.append({"action": "open_url", "target": target_url})
            summary = f"Opening Google search for {search_phrase}."
            return {"summary": summary, "steps": steps}

        if url_or_domain:
            steps.append({"action": "open_url", "target": url_or_domain})
            steps.append({"action": "wait", "payload": {"seconds": 1.8}})
            steps.append({"action": "type_text", "target": search_phrase})
            summary = f"Opening {url_or_domain} and typing the important search phrase."
            return {"summary": summary, "steps": steps}

        target_url = f"https://www.google.com/search?q={urlencode({'q': search_phrase})[2:]}"
        steps.append({"action": "open_url", "target": target_url})
        summary = f"Opening a browser search for {search_phrase}."
        return {"summary": summary, "steps": steps}

    if url_or_domain:
        steps.append({"action": "open_url", "target": url_or_domain})
        summary = f"Opening {url_or_domain} in the default browser."

    if typed_instruction and not is_complex_site_workflow(normalized):
        if steps:
            steps.append({"action": "wait", "payload": {"seconds": 1.8}})
        steps.append({"action": "type_text", "target": typed_instruction})
        summary = "Opening the requested page and typing the important message into the active field."
        return {"summary": summary, "steps": steps}

    if email_value or password_value:
        if not steps and not url_or_domain:
            summary = "Typing the provided credentials into the active browser fields."
        elif steps:
            steps.append({"action": "wait", "payload": {"seconds": 2.0}})
            summary = f"{summary} Then filling the credentials into the active fields."

        sequence = [value for value in [email_value, password_value] if value]
        steps.append({"action": "type_sequence", "payload": {"values": sequence, "submit": "login" in lowered or "sign in" in lowered}})
        return {"summary": summary, "steps": steps}

    if message_value:
        steps.append({"action": "type_text", "target": message_value})
        summary = "Typing the provided message into the active browser field."
        return {"summary": summary, "steps": steps}

    if any(token in lowered for token in ["type ", "write ", "send "]) and not message_value and not is_complex_site_workflow(normalized):
        typed_text = normalized
        for prefix in ["type", "write", "send"]:
            if lowered.startswith(prefix):
                typed_text = normalized[len(prefix):].strip(" :")
                break
        steps.append({"action": "type_text", "target": typed_text})
        summary = "Typing the requested text into the active app or browser field."
        return {"summary": summary, "steps": steps}

    if not steps:
        target_url = f"https://www.google.com/search?q={urlencode({'q': normalized})[2:]}"
        steps.append({"action": "open_url", "target": target_url})
        summary = "Opening a browser search based on the important part of your prompt."

    return {"summary": summary, "steps": steps}


def get_social_connection_status(connection: IntegrationConnection) -> tuple[bool, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    if connection.metadata_json:
        try:
            metadata = json.loads(connection.metadata_json)
        except json.JSONDecodeError:
            metadata = {}

    configured = bool(metadata.get("configured")) and connection.is_connected
    return configured, metadata


def social_public_base_url() -> str:
    return os.getenv("AKANSHA_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _local_secret_key() -> bytes:
    seed = os.getenv("AKANSHA_SECRET_KEY") or os.getenv("SECRET_KEY") or "akansha-local-dev-secret"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _local_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def _local_encrypt(raw: bytes) -> dict[str, str]:
    key = _local_secret_key()
    nonce = secrets.token_bytes(16)
    stream = _local_keystream(key, nonce, len(raw))
    ciphertext = bytes(item ^ stream[index] for index, item in enumerate(raw))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        "scheme": "local-hmac-stream-v1",
        "payload": base64.b64encode(nonce + tag + ciphertext).decode("ascii"),
    }


def _local_decrypt(payload: str) -> bytes:
    key = _local_secret_key()
    packed = base64.b64decode(payload.encode("ascii"))
    nonce, tag, ciphertext = packed[:16], packed[16:48], packed[48:]
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Social credential signature did not match.")
    stream = _local_keystream(key, nonce, len(ciphertext))
    return bytes(item ^ stream[index] for index, item in enumerate(ciphertext))


def _dpapi_encrypt(raw: bytes) -> dict[str, str]:
    if os.name != "nt":
        raise RuntimeError("DPAPI is only available on Windows.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(raw)
    in_blob = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return {"scheme": "windows-dpapi", "payload": base64.b64encode(encrypted).decode("ascii")}


def _dpapi_decrypt(payload: str) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI is only available on Windows.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    encrypted = base64.b64decode(payload.encode("ascii"))
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(encrypted)
    in_blob = DataBlob(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def encrypt_social_config(config: dict[str, str]) -> dict[str, str]:
    raw = json.dumps(config, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if os.name == "nt":
        try:
            return _dpapi_encrypt(raw)
        except Exception:
            pass
    return _local_encrypt(raw)


def decrypt_social_config(metadata: dict[str, Any]) -> dict[str, str]:
    encrypted = metadata.get("config_encrypted")
    if isinstance(encrypted, dict) and isinstance(encrypted.get("payload"), str):
        try:
            scheme = encrypted.get("scheme")
            if scheme == "windows-dpapi":
                raw = _dpapi_decrypt(encrypted["payload"])
            else:
                raw = _local_decrypt(encrypted["payload"])
            decoded = json.loads(raw.decode("utf-8"))
            if isinstance(decoded, dict):
                return {str(key): str(value) for key, value in decoded.items()}
        except Exception:
            return {}

    legacy_config = metadata.get("config")
    if isinstance(legacy_config, dict):
        return {str(key): str(value) for key, value in legacy_config.items()}
    return {}


def ensure_social_auto_secrets(platform: str, config: dict[str, str]) -> dict[str, str]:
    updated = dict(config)
    if platform in {"whatsapp", "instagram"} and not updated.get("webhook_verify_token"):
        updated["webhook_verify_token"] = secrets.token_urlsafe(24)
    if platform == "telegram" and not updated.get("webhook_secret"):
        updated["webhook_secret"] = secrets.token_urlsafe(24)
    return updated


def clean_social_config(platform: str, config: dict[str, str]) -> dict[str, str]:
    allowed = {field["key"] for field in SOCIAL_FIELD_DEFINITIONS.get(platform, [])}
    cleaned: dict[str, str] = {}
    for key, value in config.items():
        if key in allowed and isinstance(value, str) and value.strip():
            cleaned[key] = value.strip()
    return cleaned


def social_config_preview(platform: str, config: dict[str, str]) -> dict[str, str]:
    secret_fields = {
        field["key"]
        for field in SOCIAL_FIELD_DEFINITIONS.get(platform, [])
        if field.get("secret")
    }
    return {
        key: mask_secret(value) if key in secret_fields else value
        for key, value in config.items()
    }


def serialize_social_platform(platform: str, connection: IntegrationConnection) -> dict[str, Any]:
    meta = SOCIAL_PLATFORM_META[platform]
    configured, metadata = get_social_connection_status(connection)
    config = decrypt_social_config(metadata)
    required_fields = SOCIAL_REQUIRED_FIELDS.get(platform, [])
    configured_fields = sorted(config.keys())
    missing_fields = [field for field in required_fields if not config.get(field)]
    verified = bool(metadata.get("verified"))
    return {
        "key": platform,
        "label": meta["label"],
        "connected": configured,
        "verified": verified,
        "accent": meta["accent"],
        "setup_required": bool(missing_fields),
        "required_fields": required_fields,
        "missing_fields": missing_fields,
        "configured_fields": configured_fields,
        "fields": SOCIAL_FIELD_DEFINITIONS.get(platform, []),
        "config_preview": social_config_preview(platform, config),
        "webhook_url": f"{social_public_base_url()}/api/social/webhook/{platform}",
        "last_verified": metadata.get("last_verified"),
        "verification_status": metadata.get("verification_status") or ("verified" if verified else "not_tested"),
        "verification_detail": metadata.get("verification_detail"),
        "account_label": connection.account_email if configured else None,
    }


def verify_social_config(platform: str, config: dict[str, str]) -> dict[str, Any]:
    if platform == "telegram":
        bot_token = config.get("bot_token", "")
        request = Request(f"https://api.telegram.org/bot{bot_token}/getMe")
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise HTTPException(status_code=400, detail="Telegram rejected this bot token.")
        result = data.get("result", {})
        username = result.get("username") or result.get("first_name") or "Telegram bot"
        return {
            "verified": True,
            "verification_status": "verified",
            "account_label": f"@{username}" if not str(username).startswith("@") else username,
            "detail": "Telegram bot token verified with getMe.",
        }

    if platform == "whatsapp":
        token = config.get("access_token")
        phone_number_id = config.get("phone_number_id")
        if token and phone_number_id:
            request = Request(
                f"https://graph.facebook.com/v19.0/{phone_number_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            return {
                "verified": True,
                "verification_status": "verified",
                "account_label": data.get("display_phone_number") or data.get("verified_name") or "WhatsApp Cloud API",
                "detail": "WhatsApp phone number ID verified with Meta Graph API.",
            }

    if platform == "instagram":
        token = config.get("page_access_token")
        account_id = config.get("instagram_business_account_id")
        if token and account_id:
            request = Request(
                f"https://graph.facebook.com/v19.0/{account_id}?fields=username",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            username = data.get("username") or account_id
            return {
                "verified": True,
                "verification_status": "verified",
                "account_label": f"@{username}" if not str(username).startswith("@") else username,
                "detail": "Instagram business account verified with Meta Graph API.",
            }

    if platform == "twitter":
        token = config.get("bearer_token")
        if token:
            request = Request(
                "https://api.x.com/2/users/by/username/xdevelopers",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            user = data.get("data", {})
            return {
                "verified": True,
                "verification_status": "verified",
                "account_label": "X API bearer token",
                "detail": f"X bearer token verified with a public user lookup ({user.get('username', 'xdevelopers')}).",
            }

    return {
        "verified": False,
        "verification_status": "configured_unverified",
        "account_label": f"{platform}@configured.local",
        "detail": "Credentials were saved. Live verification was skipped for this platform.",
    }


def store_social_message(db: Session, platform: str, sender: str, content: str, intent: str = "incoming") -> None:
    if not content.strip():
        return
    db.add(
        InboxMessage(
            platform=platform,
            sender=sender or "Unknown",
            content=content.strip(),
            intent=intent,
            sentiment="neutral",
            is_read=False,
        )
    )


def get_connection_metadata(connection: IntegrationConnection) -> dict[str, Any]:
    if not connection.metadata_json:
        return {}
    try:
        return json.loads(connection.metadata_json)
    except json.JSONDecodeError:
        return {}


def get_browser_automation_status(connection: IntegrationConnection) -> dict[str, Any]:
    metadata = get_connection_metadata(connection)
    permissions = {
        **BROWSER_AUTOMATION_DEFAULTS,
        **metadata.get("permissions", {}),
    }
    scheduled_actions = metadata.get("scheduled_actions", [])
    return {
        "provider": BROWSER_AUTOMATION_PROVIDER,
        "permissions": permissions,
        "scheduled_actions": scheduled_actions,
        "actions": BROWSER_AUTOMATION_ACTIONS,
        "disclaimer": (
            "Akansha can prepare and trigger browser actions, but the browser and OS still enforce "
            "their own security and focus rules."
        ),
    }


def ensure_social_seed(db: Session):
    existing = (
        db.query(InboxMessage)
        .filter(InboxMessage.platform.in_(list(SOCIAL_PLATFORM_META.keys())))
        .count()
    )
    if existing:
        return

    samples = [
        InboxMessage(
            platform="whatsapp",
            sender="Rahul",
            content="Hey, can we move tomorrow's practice interview to 7:30 PM?",
            intent="schedule",
            sentiment="neutral",
        ),
        InboxMessage(
            platform="instagram",
            sender="Ananya Design",
            content="Loved your AI project post. Are you open to collaborating on a reel next week?",
            intent="collaboration",
            sentiment="positive",
        ),
        InboxMessage(
            platform="twitter",
            sender="Open Source Club",
            content="We saw your thread on JWT refresh flow. Would you like to join our Sunday space?",
            intent="invitation",
            sentiment="positive",
        ),
        InboxMessage(
            platform="telegram",
            sender="Project Team",
            content="Can you confirm whether the demo build is ready before midnight?",
            intent="status",
            sentiment="urgent",
        ),
        InboxMessage(
            platform="discord",
            sender="Build Squad",
            content="Can you review the latest bot integration notes in the shared Discord channel?",
            intent="review",
            sentiment="neutral",
        ),
    ]
    db.add_all(samples)
    db.commit()


def suggest_social_replies(message: InboxMessage) -> list[str]:
    content = message.content.lower()
    name = message.sender.split()[0]

    if any(token in content for token in ["move", "schedule", "time", "tomorrow"]):
        return [
            f"Yes {name}, 7:30 PM works for me.",
            f"I can do tomorrow, but I need a little later. Would 8 PM work?",
            "Let me confirm in a few minutes and I will get back to you.",
        ]

    if any(token in content for token in ["collab", "collaborating", "reel"]):
        return [
            "That sounds exciting. I would love to hear the idea in a little more detail.",
            "Yes, I am open to it. Can you share the concept and expected timeline?",
            "I am interested. Let us lock a quick call and plan it properly.",
        ]

    if any(token in content for token in ["join", "space", "sunday", "invite"]):
        return [
            "Thanks for inviting me. Please share the exact time and topic.",
            "I would be happy to join if the timing works. Send me the details.",
            "That sounds good. Let me check my schedule and confirm shortly.",
        ]

    if any(token in content for token in ["ready", "midnight", "demo", "confirm"]):
        return [
            "I am checking the latest build right now and will confirm shortly.",
            "The demo is almost ready. I will send a final status update soon.",
            "Give me a little time and I will confirm the final build status.",
        ]

    return [
        f"Thanks {name}, I saw your message.",
        "I am on it. Let me get back to you shortly.",
        "Got it. I will reply with a proper update soon.",
    ]


# --- OTP Auth Endpoints ---
otp_store: dict[str, str] = {}

class OTPRequest(BaseModel):
    email: str

class OTPVerifyRequest(BaseModel):
    email: str
    code: str

@app.post("/api/auth/send-otp")
def send_otp(req: OTPRequest):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    if not req.email:
        raise HTTPException(status_code=400, detail="Email is required.")
    
    code = f"{secrets.randbelow(1000000):06d}"
    otp_store[req.email.lower()] = code
    
    print(f"\n[{datetime.now().isoformat()}] OTP generated for {req.email}: {code}\n")
    
    # SMTP Sending Logic
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if smtp_email and smtp_password:
        try:
            msg = MIMEMultipart()
            # Note: Gmail SMTP often requires the 'From' address to be exactly the authenticated email
            msg['From'] = smtp_email
            msg['To'] = req.email
            msg['Subject'] = f"{code} is your Akansha Verification Sequence"

            body = f"""
[ AUTHENTICATION SEQUENCE INITIALIZED ]

Hello Operator,

Your secure identity verification code is: {code}

Please enter this sequence in the Wwise Enchart Autonomous Agent interface to complete your uplink.
This sequence is valid for a single session and will expire shortly.

If you did not request this sequence, please ignore this transmission.

[ SYSTEM STATUS: SECURE ]
[ UPLINK ORIGIN: AKANSHA_AI_ENGINE ]
            """
            msg.attach(MIMEText(body, 'plain'))

            print(f"Connecting to {smtp_server}:{smtp_port}...")
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, req.email, msg.as_string())
            server.quit()
            print(f"Email successfully dispatched to {req.email}")
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to dispatch email: {e}")
    else:
        print("WARNING: SMTP credentials missing. Email dispatch skipped.")
    
    return {"success": True, "message": f"OTP sent to {req.email}"}

@app.post("/api/auth/verify-otp")
def verify_otp(req: OTPVerifyRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    if email not in otp_store or otp_store[email] != req.code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code.")
    
    del otp_store[email]
    
    user = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not user:
        user = UserProfile(email=email, full_name=email.split('@')[0])
        db.add(user)
        db.commit()
        db.refresh(user)
    
    return {
        "success": True, 
        "token": f"mock-jwt-token-{secrets.token_hex(8)}", 
        "user": {
            "email": user.email, 
            "full_name": user.full_name
        }
    }

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not req.message:
        raise HTTPException(status_code=400, detail="Message is empty")

    # Save User Message
    user_msg = ChatMessage(role="user", content=req.message, session_id=req.session_id)
    db.add(user_msg)
    db.commit()

    try:
        # Generate Response
        response_generator = generate_chat_stream(
            db,
            req.message,
            req.session_id,
            user_tone=req.user_tone,
            response_style=req.response_style,
            conversation_mode=req.conversation_mode,
            language_preference=req.language_preference,
        )
        response_text = "".join(list(response_generator))
        
        # Save Assistant Message
        ai_msg = ChatMessage(role="assistant", content=response_text, session_id=req.session_id)
        db.add(ai_msg)
        db.commit()

        # Background Task: Extract Memories & Tasks
        background_tasks.add_task(analyze_intent_and_memory, db, req.message, response_text)

        return {"response": response_text}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI Engine Error: {str(e)}")


@app.post("/api/chat/message")
def save_chat_message(req: ChatMessageSaveRequest, db: Session = Depends(get_db)):
    if req.role not in {"user", "assistant"}:
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'assistant'.")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Message content is empty.")

    message = ChatMessage(
        role=req.role,
        content=req.content.strip(),
        session_id=req.session_id or "default",
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "message": {
            "id": message.id,
            "session_id": message.session_id,
            "role": message.role,
            "content": message.content,
            "timestamp": message.timestamp.isoformat() if message.timestamp else None,
        }
    }


@app.post("/api/chat/stream")
async def chat_stream_endpoint(
    req: ChatRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    if not req.message:
        raise HTTPException(status_code=400, detail="Message is empty")

    user_msg = ChatMessage(role="user", content=req.message, session_id=req.session_id)
    db.add(user_msg)
    db.commit()

    async def event_stream():
        response_text = ""
        try:
            for chunk in generate_chat_stream(
                db,
                req.message,
                req.session_id,
                user_tone=req.user_tone,
                response_style=req.response_style,
                conversation_mode=req.conversation_mode,
                language_preference=req.language_preference,
            ):
                response_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            ai_msg = ChatMessage(role="assistant", content=response_text, session_id=req.session_id)
            db.add(ai_msg)
            db.commit()
            background_tasks.add_task(analyze_intent_and_memory, db, req.message, response_text)
            yield f"data: {json.dumps({'type': 'done', 'content': response_text})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/api/chat")
def get_chat_history(session_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ChatMessage)
    if session_id:
        query = query.filter(ChatMessage.session_id == session_id)

    messages = query.order_by(ChatMessage.id.asc()).all()
    return {
        "messages": [
            {
                "id": m.id,
                "session_id": m.session_id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
                if hasattr(m, "timestamp") and m.timestamp
                else None,
            }
            for m in messages
        ]
    }


@app.delete("/api/chat/session/{session_id}")
def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="Session id is required.")

    deleted_count = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == normalized_session_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {
        "success": True,
        "session_id": normalized_session_id,
        "deleted": deleted_count,
    }


@app.delete("/api/chat/history")
def clear_chat_history(db: Session = Depends(get_db)):
    deleted_count = db.query(ChatMessage).delete(synchronize_session=False)
    db.commit()
    return {"success": True, "deleted": deleted_count}


@app.get("/api/memories")
def get_memories(db: Session = Depends(get_db)):
    memories = db.query(Memory).order_by(Memory.importance.desc()).all()
    return {"memories": [{"id": m.id, "topic": m.topic, "insight": m.insight, "importance": m.importance, "timestamp": m.timestamp.isoformat() if hasattr(m, 'timestamp') and m.timestamp else None} for m in memories]}

@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db)):
    tasks = db.query(Task).filter(Task.is_completed == False).order_by(Task.timestamp.desc()).all()
    return {"tasks": [{"id": t.id, "title": t.title, "description": t.description} for t in tasks]}

@app.get("/api/inbox")
def get_inbox(db: Session = Depends(get_db)):
    messages = db.query(InboxMessage).order_by(InboxMessage.timestamp.desc()).limit(20).all()
    return {"inbox": [{"platform": m.platform, "sender": m.sender, "content": m.content, "intent": m.intent} for m in messages]}


@app.get("/api/social/inbox")
def get_social_inbox(db: Session = Depends(get_db)):
    ensure_social_seed(db)
    messages = (
        db.query(InboxMessage)
        .filter(InboxMessage.platform.in_(list(SOCIAL_PLATFORM_META.keys())))
        .order_by(InboxMessage.timestamp.desc())
        .limit(12)
        .all()
    )

    platforms = []
    for key, meta in SOCIAL_PLATFORM_META.items():
        connection = get_or_create_connection(db, key)
        platforms.append(serialize_social_platform(key, connection))

    return {
        "platforms": platforms,
        "messages": [
            {
                "id": message.id,
                "platform": message.platform,
                "sender": message.sender,
                "content": message.content,
                "intent": message.intent or "general",
                "sentiment": message.sentiment or "neutral",
                "is_read": message.is_read,
                "timestamp": message.timestamp.isoformat() if message.timestamp else None,
                "suggested_replies": suggest_social_replies(message),
            }
            for message in messages
        ],
    }


@app.post("/api/social/connect/{platform}")
def connect_social_platform(platform: str, db: Session = Depends(get_db)):
    if platform not in SOCIAL_PLATFORM_META:
        raise HTTPException(status_code=404, detail="Unsupported social platform")

    connection = get_or_create_connection(db, platform)
    configured, metadata = get_social_connection_status(connection)
    if not configured:
        raise HTTPException(
            status_code=400,
            detail="This platform is not configured yet. Add the required API credentials first.",
        )

    config = decrypt_social_config(metadata)
    try:
        verification = verify_social_config(platform, config)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or str(exc)
        raise HTTPException(status_code=400, detail=f"{platform} verification failed: {detail}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{platform} verification failed: {exc}") from exc

    metadata.update(
        {
            "verified": verification["verified"],
            "verification_status": verification["verification_status"],
            "verification_detail": verification["detail"],
            "last_verified": datetime.now(timezone.utc).isoformat(),
        }
    )
    connection.account_email = verification.get("account_label")
    connection.metadata_json = json.dumps(metadata)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return {"success": True, "platform": platform, "status": serialize_social_platform(platform, connection)}


@app.post("/api/social/setup/{platform}")
def setup_social_platform(platform: str, req: SocialSetupRequest, db: Session = Depends(get_db)):
    if platform not in SOCIAL_PLATFORM_META:
        raise HTTPException(status_code=404, detail="Unsupported social platform")

    required_fields = SOCIAL_REQUIRED_FIELDS.get(platform, [])
    config = ensure_social_auto_secrets(platform, clean_social_config(platform, req.config))
    missing = [field for field in required_fields if not config.get(field, "").strip()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    verification: dict[str, Any] = {
        "verified": False,
        "verification_status": "saved_not_tested",
        "account_label": f"{platform}@configured.local",
        "detail": "Credentials saved. Use Test connection to verify them live.",
    }
    if req.test_connection:
        try:
            verification = verify_social_config(platform, config)
        except HTTPError as exc:
            verification = {
                "verified": False,
                "verification_status": "verification_failed",
                "account_label": f"{platform}@configured.local",
                "detail": exc.read().decode("utf-8", errors="ignore") or str(exc),
            }
        except Exception as exc:
            verification = {
                "verified": False,
                "verification_status": "verification_failed",
                "account_label": f"{platform}@configured.local",
                "detail": str(exc),
            }

    connection = get_or_create_connection(db, platform)
    connection.is_connected = True
    connection.account_email = verification.get("account_label")
    connection.access_token = None
    connection.metadata_json = json.dumps(
        {
            "mode": "manual-api-config",
            "configured": True,
            "configured_fields": sorted(config.keys()),
            "config_encrypted": encrypt_social_config(config),
            "config": None,
            "security": "tokens-encrypted-at-rest",
            "verified": verification["verified"],
            "verification_status": verification["verification_status"],
            "verification_detail": verification["detail"],
            "last_verified": datetime.now(timezone.utc).isoformat() if verification["verified"] else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)

    return {
        "success": True,
        "platform": platform,
        "configured_fields": sorted(config.keys()),
        "status": serialize_social_platform(platform, connection),
        "verification_detail": verification["detail"],
    }


@app.post("/api/social/disconnect/{platform}")
def disconnect_social_platform(platform: str, db: Session = Depends(get_db)):
    if platform not in SOCIAL_PLATFORM_META:
        raise HTTPException(status_code=404, detail="Unsupported social platform")

    connection = get_or_create_connection(db, platform)
    connection.is_connected = False
    connection.access_token = None
    connection.refresh_token = None
    connection.scope = None
    connection.account_email = None
    connection.metadata_json = json.dumps(
        {
            "mode": "manual-api-config",
            "configured": False,
            "configured_fields": [],
            "last_verified": None,
        }
    )
    db.add(connection)
    db.commit()

    return {"success": True, "platform": platform}


@app.get("/api/social/webhook/{platform}")
def verify_social_webhook(platform: str, request: FastAPIRequest, db: Session = Depends(get_db)):
    if platform not in SOCIAL_PLATFORM_META:
        raise HTTPException(status_code=404, detail="Unsupported social platform")

    connection = get_or_create_connection(db, platform)
    _, metadata = get_social_connection_status(connection)
    config = decrypt_social_config(metadata)

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected = config.get("webhook_verify_token") or config.get("webhook_secret")

    if mode == "subscribe" and challenge and expected and token == expected:
        return Response(content=challenge, media_type="text/plain")

    raise HTTPException(status_code=403, detail="Webhook verification token did not match.")


@app.post("/api/social/webhook/{platform}")
async def receive_social_webhook(platform: str, request: FastAPIRequest, db: Session = Depends(get_db)):
    if platform not in SOCIAL_PLATFORM_META:
        raise HTTPException(status_code=404, detail="Unsupported social platform")

    payload = await request.json()
    stored = 0

    if platform == "telegram":
        message = payload.get("message") or payload.get("edited_message") or {}
        chat = message.get("chat") or {}
        sender_data = message.get("from") or {}
        sender = str(chat.get("id") or sender_data.get("username") or sender_data.get("first_name") or "Telegram")
        content = message.get("text") or message.get("caption") or ""
        if content:
            store_social_message(db, platform, sender, content)
            stored += 1

    elif platform in {"whatsapp", "instagram"}:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    sender = message.get("from") or message.get("sender", {}).get("id") or platform
                    text = (message.get("text") or {}).get("body") or message.get("message", {}).get("text") or ""
                    if text:
                        store_social_message(db, platform, str(sender), text)
                        stored += 1
            for event in entry.get("messaging", []):
                sender = str((event.get("sender") or {}).get("id") or platform)
                text = (event.get("message") or {}).get("text") or ""
                if text:
                    store_social_message(db, platform, sender, text)
                    stored += 1

    else:
        store_social_message(db, platform, platform, json.dumps(payload)[:1200], intent="webhook")
        stored += 1

    db.commit()
    return {"success": True, "platform": platform, "stored": stored}


@app.post("/api/social/send")
def send_social_reply(req: SocialReplyRequest, db: Session = Depends(get_db)):
    if req.platform not in SOCIAL_PLATFORM_META:
        raise HTTPException(status_code=404, detail="Unsupported social platform")
    if not req.approved:
        raise HTTPException(status_code=400, detail="Approval is required before Akansha can send a reply.")

    connection = get_or_create_connection(db, req.platform)
    if not connection.is_connected:
        raise HTTPException(status_code=400, detail="Connect the platform before sending replies.")
    metadata = get_connection_metadata(connection)
    config = decrypt_social_config(metadata)
    delivery_status = "approved-and-queued"
    delivery_detail = "Reply is saved locally. Add live recipient IDs/tokens to send through the platform API."

    try:
        if req.platform == "telegram":
            chat_id = config.get("default_chat_id") or (req.sender if str(req.sender).lstrip("-").isdigit() else "")
            bot_token = config.get("bot_token")
            if bot_token and chat_id:
                telegram_request = Request(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    data=json.dumps({"chat_id": chat_id, "text": req.reply}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(telegram_request, timeout=15) as response:
                    telegram_data = json.loads(response.read().decode("utf-8"))
                delivery_status = "sent"
                delivery_detail = "Telegram sendMessage accepted the reply." if telegram_data.get("ok") else "Telegram returned a non-ok response."

        elif req.platform == "whatsapp":
            recipient = re.sub(r"\D", "", req.sender)
            phone_number_id = config.get("phone_number_id")
            token = config.get("access_token")
            if token and phone_number_id and recipient:
                whatsapp_request = Request(
                    f"https://graph.facebook.com/v19.0/{phone_number_id}/messages",
                    data=json.dumps(
                        {
                            "messaging_product": "whatsapp",
                            "to": recipient,
                            "type": "text",
                            "text": {"body": req.reply},
                        }
                    ).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urlopen(whatsapp_request, timeout=15):
                    pass
                delivery_status = "sent"
                delivery_detail = "WhatsApp Cloud API accepted the reply."

        elif req.platform == "instagram":
            token = config.get("page_access_token")
            if token and req.sender and req.sender.isdigit():
                instagram_request = Request(
                    f"https://graph.facebook.com/v19.0/me/messages?access_token={token}",
                    data=json.dumps(
                        {
                            "recipient": {"id": req.sender},
                            "message": {"text": req.reply},
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(instagram_request, timeout=15):
                    pass
                delivery_status = "sent"
                delivery_detail = "Instagram Messaging API accepted the reply."
    except HTTPError as exc:
        delivery_status = "send_failed"
        delivery_detail = exc.read().decode("utf-8", errors="ignore") or str(exc)
    except Exception as exc:
        delivery_status = "send_failed"
        delivery_detail = str(exc)

    if req.message_id:
        original = db.query(InboxMessage).filter(InboxMessage.id == req.message_id).first()
        if original:
            original.is_read = True
            db.add(original)

    db.add(
        InboxMessage(
            platform=req.platform,
            sender=f"You -> {req.sender}",
            content=req.reply,
            intent="reply",
            sentiment="approved",
            is_read=True,
        )
    )
    db.commit()

    return {
        "success": True,
        "status": delivery_status,
        "detail": delivery_detail,
        "platform": req.platform,
        "sender": req.sender,
        "reply": req.reply,
    }


@app.get("/api/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    return {"profile": serialize_profile(profile)}


@app.put("/api/profile")
def update_profile(req: ProfileUpdateRequest, db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)

    for field, value in req.model_dump(exclude_none=True).items():
        setattr(profile, field, value)

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"profile": serialize_profile(profile)}


@app.get("/api/google/status")
def get_google_status(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    connection = get_or_create_connection(db, "google")
    return {
        "configured": google_configured(),
        "connected": connection.is_connected,
        "email": connection.account_email or profile.google_email,
        "scopes": connection.scope.split(" ") if connection.scope else GOOGLE_SCOPES,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "setup_required": not google_configured(),
    }


@app.get("/api/voice/status")
def get_voice_status():
    return {
        "female_cloned_voice_configured": cloned_voice_configured(),
        "provider": "edge-tts",
        "model_id": "te-IN-ShrutiNeural / en-IN-NeerjaNeural / hi-IN-SwaraNeural",
        "voice_id_present": True,
        "supported_language_modes": ["english", "telugu", "mixed", "hindi"],
    }


@app.get("/api/voice/speakers")
def get_voice_speakers(db: Session = Depends(get_db)):
    speakers = db.query(SpeakerProfile).order_by(SpeakerProfile.timestamp.asc()).all()
    return {"speakers": [serialize_speaker_profile(speaker) for speaker in speakers]}


@app.post("/api/voice/speakers")
def save_voice_speaker(req: SpeakerProfileRequest, db: Session = Depends(get_db)):
    display_name = req.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Display name is required.")

    speaker = db.query(SpeakerProfile).filter(SpeakerProfile.display_name.ilike(display_name)).first()
    if not speaker:
        speaker = SpeakerProfile(display_name=display_name)

    speaker.relationship_to_owner = req.relationship_to_owner
    speaker.access_level = req.access_level or _speaker_access_level(req.relationship_to_owner)
    speaker.notes = req.notes
    speaker.last_intro_text = (
        f"{display_name} is {req.relationship_to_owner or 'a new speaker'} for Yogesh."
    )
    db.add(speaker)
    db.commit()
    db.refresh(speaker)
    return {"speaker": serialize_speaker_profile(speaker)}


@app.post("/api/system/notify")
def system_notify(request: DesktopNotificationRequest):
    title = request.title.strip()
    body = request.body.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Notification title is required.")

    try:
        show_windows_notification(title, body or "Akansha reminder")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to show desktop notification: {exc}") from exc

    return {"success": True, "message": "Desktop notification sent."}


@app.post("/api/planner/reminders/sync")
def sync_planner_reminders(request: PlannerReminderSyncRequest):
    incoming_ids = {item.reminder_id for item in request.reminders}

    for reminder_id in list(planner_reminder_registry.keys()):
        if reminder_id not in incoming_ids:
            planner_reminder_registry.pop(reminder_id, None)
            _delete_reminder_marker(reminder_id)

    for item in request.reminders:
        existing = planner_reminder_registry.get(item.reminder_id, {})
        title = normalize_reminder_text(item.title) or "Akansha reminder"
        body = normalize_reminder_text(item.body) or "You asked Akansha to remind you."
        should_preserve_sent = bool(existing.get("sent", False)) and existing.get("reminder_at") == item.reminder_at
        armed_payload: dict[str, Any] = {}

        if not should_preserve_sent and existing.get("armed_for") != item.reminder_at:
            try:
                armed_payload = arm_detached_windows_reminder(item.reminder_id, title, body, item.reminder_at)
            except Exception as exc:
                planner_reminder_history.append({
                    "reminder_id": item.reminder_id,
                    "title": title,
                    "body": body,
                    "triggered_at": datetime.now().astimezone().isoformat(),
                    "status": f"arm_error: {exc}",
                })

        planner_reminder_registry[item.reminder_id] = {
            "title": title,
            "body": body,
            "reminder_at": item.reminder_at,
            "sent": should_preserve_sent,
            "armed_for": armed_payload.get("armed_for", existing.get("armed_for")),
            "armed_pid": armed_payload.get("pid", existing.get("armed_pid")),
            "last_synced_at": datetime.now().astimezone().isoformat(),
        }

    return {"success": True, "count": len(planner_reminder_registry)}


@app.get("/api/planner/reminders/status")
def planner_reminders_status():
    return {
        "active_count": len(planner_reminder_registry),
        "active": planner_reminder_registry,
        "history": planner_reminder_history[-20:],
        "scheduler_running": planner_scheduler_task is not None and not planner_scheduler_task.done(),
    }


@app.get("/api/automation/browser/status")
def get_browser_automation_state(db: Session = Depends(get_db)):
    connection = get_or_create_connection(db, BROWSER_AUTOMATION_PROVIDER)
    return get_browser_automation_status(connection)


@app.put("/api/automation/browser/permissions")
def update_browser_automation_permissions(
    req: BrowserAutomationPermissionsRequest, db: Session = Depends(get_db)
):
    connection = get_or_create_connection(db, BROWSER_AUTOMATION_PROVIDER)
    metadata = get_connection_metadata(connection)
    permissions = {
        **BROWSER_AUTOMATION_DEFAULTS,
        **metadata.get("permissions", {}),
    }

    for key, value in req.model_dump(exclude_none=True).items():
        permissions[key] = value

    metadata["permissions"] = permissions
    metadata["scheduled_actions"] = metadata.get("scheduled_actions", [])
    connection.is_connected = True
    connection.metadata_json = json.dumps(metadata)
    db.add(connection)
    db.commit()

    return get_browser_automation_status(connection)


@app.post("/api/automation/browser/run")
async def run_browser_automation(req: BrowserAutomationRunRequest, db: Session = Depends(get_db)):
    connection = get_or_create_connection(db, BROWSER_AUTOMATION_PROVIDER)
    status = get_browser_automation_status(connection)
    actions = {item["key"]: item for item in BROWSER_AUTOMATION_ACTIONS}
    action_meta = actions.get(req.action)

    if not action_meta:
        raise HTTPException(status_code=404, detail="Unsupported browser automation action.")

    permission_key = action_meta["permission"]
    if not status["permissions"].get(permission_key):
        raise HTTPException(
            status_code=400,
            detail=f"The '{action_meta['label']}' permission is currently turned off.",
        )

    metadata = get_connection_metadata(connection)
    metadata["permissions"] = status["permissions"]
    scheduled_actions = metadata.get("scheduled_actions", [])

    if req.run_at:
        scheduled_action = {
            "id": secrets.token_hex(6),
            "action": req.action,
            "label": action_meta["label"],
            "target": req.target,
            "run_at": req.run_at,
            "background": req.background,
            "status": "scheduled",
            "created_at": datetime.utcnow().isoformat(),
            "note": (
                "Saved inside Akansha as a planned browser action. Automatic timed execution still "
                "depends on keeping a worker running."
            ),
        }
        scheduled_actions.append(scheduled_action)
        metadata["scheduled_actions"] = scheduled_actions
        connection.is_connected = True
        connection.metadata_json = json.dumps(metadata)
        db.add(connection)
        db.commit()
        return {
            "success": True,
            "scheduled": True,
            "message": f"{action_meta['label']} saved for {req.run_at}.",
            "scheduled_action": scheduled_action,
        }

    result = await execute_desktop_command(
        req.action,
        req.target,
        {"background": req.background},
    )
    return {
        "success": bool(result.get("success")),
        "scheduled": False,
        "message": result.get("message"),
        "note": result.get("note"),
    }


@app.post("/api/automation/browser/prompt")
async def run_browser_automation_prompt(req: BrowserAutomationPromptRequest, db: Session = Depends(get_db)):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Automation prompt is empty.")

    inferred_run_at, cleaned_prompt = extract_prompt_schedule(prompt)
    effective_run_at = req.run_at or inferred_run_at
    planning_prompt = cleaned_prompt.strip() or prompt

    connection = get_or_create_connection(db, BROWSER_AUTOMATION_PROVIDER)
    metadata = get_connection_metadata(connection)
    metadata["permissions"] = {**BROWSER_AUTOMATION_DEFAULTS}
    scheduled_actions = metadata.get("scheduled_actions", [])

    plan = build_browser_prompt_plan(planning_prompt)

    if plan.get("needs_clarification"):
        return {
            "success": True,
            "scheduled": False,
            "message": plan["summary"],
            "plan": plan,
            "requires_clarification": True,
        }

    if effective_run_at:
        scheduled_action = {
            "id": secrets.token_hex(6),
            "action": "freeform-prompt",
            "label": plan["summary"],
            "target": planning_prompt,
            "run_at": effective_run_at,
            "background": req.background,
            "status": "scheduled",
            "created_at": datetime.utcnow().isoformat(),
            "note": "Saved from the freeform automation box.",
        }
        scheduled_actions.append(scheduled_action)
        metadata["scheduled_actions"] = scheduled_actions
        connection.is_connected = True
        connection.metadata_json = json.dumps(metadata)
        db.add(connection)
        db.commit()
        _schedule_automation_plan(effective_run_at, plan, planning_prompt)
        return {
            "success": True,
            "scheduled": True,
            "message": f"{plan['summary']} Saved for {effective_run_at}.",
            "plan": plan,
        }

    execution_results = []
    for step in plan["steps"]:
        result = await execute_desktop_command(
            step["action"],
            step.get("target"),
            step.get("payload"),
        )
        execution_results.append({"step": step, "result": result})
        if not result.get("success"):
            break

    final_result = execution_results[-1]["result"] if execution_results else {"success": False, "message": "No steps were executed."}
    result_message = (final_result.get("message") or "").strip()
    plan_summary = str(plan.get("summary", "")).strip()
    if final_result.get("success") and plan_summary:
        if result_message and result_message.lower() != plan_summary.lower():
            response_message = f"{plan_summary} {result_message}".strip()
        else:
            response_message = plan_summary
    else:
        response_message = result_message or plan_summary or "I could not complete that automation request."
    return {
        "success": bool(final_result.get("success")),
        "scheduled": False,
        "message": response_message,
        "plan": plan,
        "results": execution_results,
        "note": (
            "This uses best-effort desktop automation. Complex site-specific flows still depend on page focus, "
            "login state, and the current browser layout."
        ),
    }


@app.delete("/api/automation/browser/scheduled/{action_id}")
def delete_scheduled_browser_automation(action_id: str, db: Session = Depends(get_db)):
    connection = get_or_create_connection(db, BROWSER_AUTOMATION_PROVIDER)
    metadata = get_connection_metadata(connection)
    scheduled_actions = metadata.get("scheduled_actions", [])
    filtered_actions = [item for item in scheduled_actions if item.get("id") != action_id]

    metadata["scheduled_actions"] = filtered_actions
    metadata["permissions"] = {
        **BROWSER_AUTOMATION_DEFAULTS,
        **metadata.get("permissions", {}),
    }
    connection.metadata_json = json.dumps(metadata)
    db.add(connection)
    db.commit()

    return {"success": True, "remaining": len(filtered_actions)}


@app.post("/api/voice/tts")
async def text_to_speech(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty.")

    try:
        audio = await generate_edge_tts_audio(
            req.text.strip(),
            req.voice_gender,
            req.voice_tone,
            req.language_mode,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {exc}")

    return Response(content=audio, media_type="audio/mpeg")


@app.get("/api/google/auth-url")
def get_google_auth_url():
    if not google_configured():
        return {
            "configured": False,
            "auth_url": None,
            "message": "Add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI to enable Google OAuth.",
        }

    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "scope": " ".join(GOOGLE_SCOPES),
            "state": state,
        }
    )
    return {
        "configured": True,
        "auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
        "state": state,
    }


@app.get("/api/google/callback")
def google_callback(code: str, db: Session = Depends(get_db)):
    if not google_configured():
        raise HTTPException(status_code=400, detail="Google OAuth is not configured.")

    token_request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    with urlopen(token_request, timeout=20) as response:
        token_payload = json.loads(response.read().decode("utf-8"))

    access_token = token_payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail="Google did not return an access token.")

    user_info_request = Request(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urlopen(user_info_request, timeout=20) as response:
        user_info = json.loads(response.read().decode("utf-8"))

    profile = get_or_create_profile(db)
    connection = get_or_create_connection(db, "google")
    update_google_connection(db, connection, profile, token_payload, user_info)

    return {
        "success": True,
        "email": user_info.get("email"),
        "message": "Google account connected. You can return to Akansha now.",
    }


@app.post("/api/google/disconnect")
def disconnect_google(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    connection = get_or_create_connection(db, "google")

    connection.access_token = None
    connection.refresh_token = None
    connection.scope = None
    connection.account_email = None
    connection.token_expiry = None
    connection.metadata_json = None
    connection.is_connected = False

    profile.google_connected = False
    profile.google_email = None

    db.add(connection)
    db.add(profile)
    db.commit()

    return {"success": True}


@app.get("/api/google/gmail/summary")
def get_gmail_summary(db: Session = Depends(get_db)):
    connection = get_or_create_connection(db, "google")
    if not connection.is_connected or not connection.access_token:
        return {
            "connected": False,
            "summary": "Connect Google to read and summarize Gmail threads from Akansha.",
            "emails": [],
        }

    try:
        messages = google_api_get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=5&q=category:primary",
            connection,
        )
        email_cards = []
        for item in messages.get("messages", []):
            message_data = google_api_get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject",
                connection,
            )
            headers = {
                header["name"]: header["value"]
                for header in message_data.get("payload", {}).get("headers", [])
            }
            email_cards.append(
                {
                    "id": item["id"],
                    "sender": headers.get("From", "Unknown sender"),
                    "subject": headers.get("Subject", "No subject"),
                    "snippet": message_data.get("snippet", ""),
                    "important": "IMPORTANT" in message_data.get("labelIds", []),
                }
            )

        summary = (
            f"You have {len(email_cards)} recent Gmail threads ready for review."
            if email_cards
            else "No recent Gmail threads were found."
        )
        return {"connected": True, "summary": summary, "emails": email_cards}
    except Exception as exc:
        return {
            "connected": True,
            "summary": f"Gmail is connected, but Akansha could not fetch messages right now: {exc}",
            "emails": [],
        }


@app.get("/api/google/calendar/events")
def get_calendar_events(db: Session = Depends(get_db)):
    connection = get_or_create_connection(db, "google")
    if not connection.is_connected or not connection.access_token:
        return {
            "connected": False,
            "events": [
                {
                    "title": "Connect Google Calendar",
                    "start": "Anytime",
                    "description": "Authorize Google to view upcoming events and create reminders.",
                }
            ],
        }

    try:
        now = datetime.now(timezone.utc).isoformat()
        events_data = google_api_get(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=5&singleEvents=true&orderBy=startTime&timeMin={now}",
            connection,
        )
        events = [
            {
                "id": item.get("id"),
                "title": item.get("summary", "Untitled event"),
                "start": item.get("start", {}).get("dateTime") or item.get("start", {}).get("date"),
                "description": item.get("description", ""),
            }
            for item in events_data.get("items", [])
        ]
        return {"connected": True, "events": events}
    except Exception as exc:
        return {
            "connected": True,
            "events": [],
            "error": f"Calendar is connected, but events could not be loaded: {exc}",
        }


@app.post("/api/google/calendar/reminders")
def create_calendar_reminder(req: ReminderRequest, db: Session = Depends(get_db)):
    connection = get_or_create_connection(db, "google")
    if not connection.is_connected or not connection.access_token:
        raise HTTPException(status_code=400, detail="Connect Google Calendar before creating reminders.")

    event_payload = {
        "summary": req.title,
        "start": {"dateTime": req.date_time},
        "end": {"dateTime": req.date_time},
    }
    request = Request(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        data=json.dumps(event_payload).encode("utf-8"),
        headers={
            **google_auth_headers(connection),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        created = json.loads(response.read().decode("utf-8"))

    return {
        "success": True,
        "event_id": created.get("id"),
        "html_link": created.get("htmlLink"),
    }

# Mount frontend files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
