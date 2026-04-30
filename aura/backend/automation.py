import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote_plus

import fitz
import pyautogui
from pptx import Presentation
from pptx.util import Inches

pyautogui.FAILSAFE = False


APP_LAUNCH_COMMANDS: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "file explorer": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "vscode": ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "chrome": ["chrome.exe"],
    "brave": ["brave.exe"],
    "edge": ["msedge.exe"],
    "command prompt": ["cmd.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
}

SPECIAL_FOLDERS: dict[str, Path] = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
}


def _launch_windows_app(app_name: str) -> str:
    normalized = app_name.strip().lower()
    if not normalized:
        raise ValueError("An app name is required.")

    commands = APP_LAUNCH_COMMANDS.get(normalized, [normalized])
    last_error: Exception | None = None

    for command in commands:
        try:
            resolved = shutil.which(command) or command
            subprocess.Popen([resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return normalized
        except Exception as exc:  # pragma: no cover - best effort on host desktop
            last_error = exc

    raise RuntimeError(f"Could not open app '{app_name}': {last_error}")


def _resolve_folder_path(target: str | None, payload: dict | None = None) -> Path:
    payload = payload or {}
    raw_target = (target or payload.get("path") or payload.get("source_path") or "").strip().strip('"')
    if raw_target:
        candidate = Path(raw_target).expanduser()
        return candidate

    folder_key = str(payload.get("folder_key", "")).strip().lower()
    if folder_key in SPECIAL_FOLDERS:
        return SPECIAL_FOLDERS[folder_key]

    raise ValueError("A folder path is required.")


def _create_folder(base_path: Path, folder_name: str) -> Path:
    if not folder_name.strip():
        raise ValueError("A folder name is required.")
    created = base_path / folder_name.strip()
    created.mkdir(parents=True, exist_ok=True)
    return created


def _convert_pdfs_in_folder_to_ppts(source_path: Path, output_folder_name: str) -> dict[str, str | int]:
    if not source_path.exists() or not source_path.is_dir():
        raise ValueError(f"Source folder does not exist: {source_path}")

    output_dir = _create_folder(source_path, output_folder_name or "Converted_PPTs")
    pdf_files = sorted(source_path.glob("*.pdf"))
    if not pdf_files:
        raise ValueError(f"No PDF files found in {source_path}")

    converted_count = 0

    for pdf_file in pdf_files:
        presentation = Presentation()
        presentation.slide_width = Inches(13.333)
        presentation.slide_height = Inches(7.5)

        with fitz.open(pdf_file) as document:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_image:
                    temp_path = Path(temp_image.name)
                try:
                    pixmap.save(temp_path.as_posix())
                    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
                    slide.shapes.add_picture(
                        str(temp_path),
                        0,
                        0,
                        width=presentation.slide_width,
                        height=presentation.slide_height,
                    )
                finally:
                    if temp_path.exists():
                        temp_path.unlink(missing_ok=True)

        output_file = output_dir / f"{pdf_file.stem}.pptx"
        presentation.save(str(output_file))
        converted_count += 1

    return {
        "output_dir": str(output_dir),
        "converted_count": converted_count,
    }


def _open_external_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("A URL or search target is required.")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    if hasattr(os, "startfile"):
        os.startfile(normalized)  # type: ignore[attr-defined]
    else:
        import webbrowser

        webbrowser.open(normalized, new=2)
    return normalized


def _extract_amount(payload: dict, default: int = 5) -> int:
    raw_value = payload.get("amount", payload.get("steps", payload.get("value", default)))
    try:
        parsed = int(float(str(raw_value)))
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, 100))


def _set_windows_brightness(value: int) -> int:
    safe_value = max(0, min(int(value), 100))
    command = (
        "$monitor = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
        "-ErrorAction Stop | Select-Object -First 1; "
        f"Invoke-CimMethod -InputObject $monitor -MethodName WmiSetBrightness "
        f"-Arguments @{{Timeout=1;Brightness={safe_value}}} | Out-Null"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Windows brightness control is unavailable on this display.")
    return safe_value


def _get_windows_brightness() -> int:
    command = (
        "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
        "-ErrorAction Stop | Select-Object -First 1).CurrentBrightness"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Windows brightness status is unavailable on this display.")
    match = re.search(r"\d+", completed.stdout)
    if not match:
        raise RuntimeError("Windows did not return a current brightness value.")
    return max(0, min(int(match.group(0)), 100))


async def execute_desktop_command(action: str, target: str = None, payload: dict | None = None):
    """Executes desktop and browser automation commands with best-effort safety."""
    payload = payload or {}

    try:
        if action == "open_notepad":
            pyautogui.press("win")
            await asyncio.sleep(0.5)
            pyautogui.write("notepad")
            await asyncio.sleep(0.5)
            pyautogui.press("enter")
            return {"success": True, "message": "Opened Notepad."}

        if action == "open_app":
            app_name = target or payload.get("app_name", "")
            opened_app = _launch_windows_app(app_name)
            return {
                "success": True,
                "message": f"Opened {opened_app}.",
                "note": "Window focus and background behavior still depend on the operating system.",
            }

        if action == "open_path":
            path = _resolve_folder_path(target, payload)
            if not path.exists():
                return {"success": False, "message": f"Path does not exist: {path}"}
            os.startfile(str(path))  # type: ignore[attr-defined]
            return {
                "success": True,
                "message": f"Opened {path} in File Explorer.",
                "note": "The operating system decides whether Explorer steals focus.",
            }

        if action == "create_folder":
            base_path = _resolve_folder_path(None, payload)
            folder_name = payload.get("folder_name", "")
            created_path = _create_folder(base_path, folder_name)
            return {
                "success": True,
                "message": f"Created folder {created_path.name}.",
                "path": str(created_path),
            }

        if action == "run_command":
            command = target or payload.get("command", "")
            shell_name = str(payload.get("shell", "powershell")).lower()
            if not command:
                return {"success": False, "message": "No command was provided."}

            if shell_name == "cmd":
                completed = subprocess.run(
                    ["cmd.exe", "/c", command],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            else:
                completed = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", command],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

            return {
                "success": completed.returncode == 0,
                "message": "Ran the requested command." if completed.returncode == 0 else "The command failed.",
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "returncode": completed.returncode,
            }

        if action == "convert_pdfs_to_ppts":
            source_path = _resolve_folder_path(None, payload)
            output_folder_name = str(payload.get("output_folder_name", "Converted_PPTs")).strip() or "Converted_PPTs"
            result = _convert_pdfs_in_folder_to_ppts(source_path, output_folder_name)
            return {
                "success": True,
                "message": f"Converted {result['converted_count']} PDF file(s) into PPTX files.",
                "output_dir": result["output_dir"],
            }

        if action == "unsupported_browser_workflow":
            return {
                "success": False,
                "message": payload.get(
                    "message",
                    "This website workflow needs a DOM-aware web agent instead of active-field typing.",
                ),
                "note": payload.get("note"),
            }

        if action in {"type", "type_text"}:
            text = target or payload.get("text")
            if not text:
                return {"success": False, "message": "No text was provided to type."}
            pyautogui.write(text, interval=0.03)
            return {"success": True, "message": f"Typed text into the active window."}

        if action == "type_sequence":
            values = payload.get("values", [])
            if not values:
                return {"success": False, "message": "No values were provided for the fill sequence."}
            tab_presses_before = int(payload.get("tab_presses_before", 0))
            clear_each = bool(payload.get("clear_each", True))
            type_interval = float(payload.get("type_interval", 0.05))
            step_delay = float(payload.get("step_delay", 0.12))
            submit_delay = float(payload.get("submit_delay", 0.2))

            for _ in range(max(0, tab_presses_before)):
                pyautogui.press("tab")
                await asyncio.sleep(step_delay)

            for index, value in enumerate(values):
                if clear_each:
                    pyautogui.hotkey("ctrl", "a")
                    await asyncio.sleep(step_delay)
                    pyautogui.press("backspace")
                    await asyncio.sleep(step_delay)
                if value:
                    pyautogui.write(str(value), interval=max(0.02, type_interval))
                if index < len(values) - 1:
                    pyautogui.press("tab")
                    await asyncio.sleep(step_delay)
            if payload.get("submit"):
                await asyncio.sleep(submit_delay)
                pyautogui.press("enter")
            return {"success": True, "message": "Typed the form sequence into the active browser fields."}

        if action == "wait":
            delay = float(payload.get("seconds", 1.0))
            await asyncio.sleep(max(0.1, min(delay, 10)))
            return {"success": True, "message": f"Waited for {delay:.1f} seconds."}

        if action == "open_url":
            opened_url = _open_external_url(target or payload.get("url", ""))
            return {
                "success": True,
                "message": f"Opened {opened_url} in the default browser.",
                "note": "The browser decides whether the new page steals focus or opens in the background.",
            }

        if action == "open_youtube_song":
            query = target or payload.get("query", "")
            if not query:
                return {"success": False, "message": "Add a song or search query first."}
            opened_url = _open_external_url(
                f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            )
            return {
                "success": True,
                "message": "Opened the YouTube search in the default browser.",
                "url": opened_url,
                "note": "Playing media in the background still depends on the browser and site autoplay rules.",
            }

        if action == "volume_up":
            presses = _extract_amount(payload, 5)
            pyautogui.press("volumeup", presses=presses, interval=0.03)
            return {"success": True, "message": f"Increased system volume by {presses} step(s)."}

        if action == "volume_down":
            presses = _extract_amount(payload, 5)
            pyautogui.press("volumedown", presses=presses, interval=0.03)
            return {"success": True, "message": f"Decreased system volume by {presses} step(s)."}

        if action in {"volume_mute", "volume_unmute"}:
            pyautogui.press("volumemute")
            return {"success": True, "message": "Toggled system mute."}

        if action == "set_brightness":
            value = _extract_amount(payload, 60)
            applied = _set_windows_brightness(value)
            return {"success": True, "message": f"Set screen brightness to {applied}%."}

        if action in {"brightness_up", "brightness_down"}:
            amount = _extract_amount(payload, 10)
            current = _get_windows_brightness()
            target_value = current + amount if action == "brightness_up" else current - amount
            applied = _set_windows_brightness(target_value)
            verb = "Increased" if action == "brightness_up" else "Decreased"
            return {"success": True, "message": f"{verb} screen brightness to {applied}%."}

        if action == "new_tab":
            pyautogui.hotkey("ctrl", "t")
            return {"success": True, "message": "Opened a new tab in the active browser window."}

        if action == "close_tab":
            pyautogui.hotkey("ctrl", "w")
            return {"success": True, "message": "Closed the current browser tab."}

        if action == "close_window":
            pyautogui.hotkey("alt", "f4")
            return {"success": True, "message": "Closed the current desktop window."}

        if action == "switch_window":
            pyautogui.hotkey("alt", "tab")
            return {"success": True, "message": "Switched to the next desktop window."}

        if action == "minimize_window":
            pyautogui.hotkey("win", "down")
            return {"success": True, "message": "Minimized the current window."}

        if action == "maximize_window":
            pyautogui.hotkey("win", "up")
            return {"success": True, "message": "Maximized the current window."}

        if action == "edit_field":
            text = target or payload.get("text", "")
            pyautogui.hotkey("ctrl", "a")
            await asyncio.sleep(0.08)
            if text:
                pyautogui.write(text, interval=0.03)
            return {"success": True, "message": "Replaced the active field content."}

        if action in {"clear_field", "remove_draft"}:
            pyautogui.hotkey("ctrl", "a")
            await asyncio.sleep(0.08)
            pyautogui.press("backspace")
            return {"success": True, "message": "Cleared the active field or draft content."}

        return {
            "success": False,
            "message": f"Automation action '{action}' is not configured yet.",
        }
    except Exception as e:
        return {"success": False, "message": f"Automation failed: {str(e)}"}
