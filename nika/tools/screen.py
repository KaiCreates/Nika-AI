"""Screen awareness and control tools for Nika.

ScreenshotTool   — capture screen + vision analysis via qwen2.5-vl (or any vision model)
ScreenControlTool — mouse clicks, keyboard, scroll via pyautogui
OpenAppTool       — launch applications by name
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import subprocess
from typing import Any

from loguru import logger

from nika.tools.base import BaseTool

# Injected at startup
_llm_client = None
_vision_model = "qwen2.5-vl:7b"


def set_screen_context(llm_client: Any, vision_model: str = "qwen2.5-vl:7b") -> None:
    global _llm_client, _vision_model
    _llm_client = llm_client
    _vision_model = vision_model


def _display_env() -> dict[str, str]:
    """Return os.environ plus a guaranteed DISPLAY / WAYLAND_DISPLAY so launched apps appear."""
    env = dict(os.environ)
    if not env.get("DISPLAY"):
        env["DISPLAY"] = ":0.0"
    return env


# ── Screenshot ─────────────────────────────────────────────────────────────────

class ScreenshotTool(BaseTool):
    name = "screenshot"
    description = (
        "Capture the current screen and describe what is visible using the vision model. "
        "Returns a detailed description including open apps, windows, text on screen, "
        "and what the user is doing."
    )
    parameters = {
        "analyze": {
            "type": "boolean",
            "description": "Send screenshot to vision model for description. Default true.",
        },
        "region": {
            "type": "string",
            "description": "Screen region: 'full' (default), 'left', 'right', 'top', 'bottom'.",
        },
        "prompt": {
            "type": "string",
            "description": "Custom question to ask about the screen.",
        },
    }
    required = []
    safety_level = "SAFE"

    last_screenshot_b64: str = ""   # shared for /screenshot web endpoint

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        analyze: bool = True,
        region: str = "full",
        prompt: str = (
            "Describe what is on this screen in detail. "
            "Mention open applications, browser tabs, any visible text, "
            "and what the user appears to be doing."
        ),
    ) -> str:
        try:
            import mss
            from PIL import Image
        except ImportError:
            return "[Error] mss/Pillow not installed. Run: pip install mss Pillow"

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                if region != "full":
                    w, h = monitor["width"], monitor["height"]
                    crops = {
                        "left":   {**monitor, "width": w // 2},
                        "right":  {**monitor, "left": monitor["left"] + w // 2, "width": w // 2},
                        "top":    {**monitor, "height": h // 2},
                        "bottom": {**monitor, "top": monitor["top"] + h // 2, "height": h // 2},
                    }
                    monitor = crops.get(region, monitor)

                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_bytes = buf.getvalue()
        except Exception as e:
            return f"[Error] Screenshot failed: {e}"

        b64 = base64.b64encode(png_bytes).decode()
        ScreenshotTool.last_screenshot_b64 = b64
        size_kb = len(png_bytes) // 1024

        if not analyze:
            return f"Screenshot captured ({shot.size[0]}x{shot.size[1]}, {size_kb}KB)."

        if _llm_client is None:
            return f"Screenshot captured ({shot.size[0]}x{shot.size[1]}, {size_kb}KB). Vision unavailable."

        try:
            description = await _llm_client.vision_chat(
                model=_vision_model,
                prompt=prompt,
                image_b64=b64,
            )
            return f"Screen ({shot.size[0]}x{shot.size[1]}):\n{description}"
        except Exception as e:
            return (
                f"Screenshot captured ({size_kb}KB) but vision analysis failed: {e}. "
                f"Make sure `{_vision_model}` is pulled: ollama pull {_vision_model}"
            )


# ── Screen Control ─────────────────────────────────────────────────────────────

class ScreenControlTool(BaseTool):
    name = "screen_control"
    description = (
        "Control the screen: click, double-click, right-click, move mouse, "
        "type text, press keyboard shortcuts, scroll, or drag. "
        "Take a screenshot first to find coordinates."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "One of: click, double_click, right_click, move, type, hotkey, scroll, drag.",
        },
        "x": {"type": "integer", "description": "X coordinate (pixels from left edge)."},
        "y": {"type": "integer", "description": "Y coordinate (pixels from top edge)."},
        "text": {"type": "string", "description": "Text to type (action='type')."},
        "keys": {"type": "array", "description": "Keys for hotkey e.g. ['ctrl','c']."},
        "scroll_amount": {"type": "integer", "description": "Scroll clicks (+up/-down). Default 3."},
        "end_x": {"type": "integer", "description": "Drag end X."},
        "end_y": {"type": "integer", "description": "Drag end Y."},
    }
    required = ["action"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        action: str,
        x: int | None = None,
        y: int | None = None,
        text: str = "",
        keys: list[str] | None = None,
        scroll_amount: int = 3,
        end_x: int | None = None,
        end_y: int | None = None,
    ) -> str:
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.05
        except ImportError:
            return "[Error] pyautogui not installed. Run: pip install pyautogui"

        os.environ.setdefault("DISPLAY", ":0.0")

        def _run() -> str:
            if action == "move":
                if x is None or y is None:
                    return "[Error] x and y required for move"
                pyautogui.moveTo(x, y, duration=0.2)
                return f"Mouse moved to ({x}, {y})"
            elif action == "click":
                if x is not None and y is not None:
                    pyautogui.click(x, y)
                    return f"Clicked at ({x}, {y})"
                pyautogui.click()
                return "Clicked at current position"
            elif action == "double_click":
                if x is not None and y is not None:
                    pyautogui.doubleClick(x, y)
                    return f"Double-clicked at ({x}, {y})"
                pyautogui.doubleClick()
                return "Double-clicked"
            elif action == "right_click":
                if x is not None and y is not None:
                    pyautogui.rightClick(x, y)
                    return f"Right-clicked at ({x}, {y})"
                pyautogui.rightClick()
                return "Right-clicked"
            elif action == "type":
                if not text:
                    return "[Error] 'text' required for type"
                pyautogui.write(text, interval=0.03)
                return f"Typed: {text[:80]}"
            elif action == "hotkey":
                if not keys:
                    return "[Error] 'keys' required for hotkey"
                pyautogui.hotkey(*keys)
                return f"Pressed: {'+'.join(keys)}"
            elif action == "scroll":
                if x is not None and y is not None:
                    pyautogui.scroll(scroll_amount, x=x, y=y)
                else:
                    pyautogui.scroll(scroll_amount)
                return f"Scrolled {'up' if scroll_amount > 0 else 'down'} {abs(scroll_amount)} clicks"
            elif action == "drag":
                if None in (x, y, end_x, end_y):
                    return "[Error] x, y, end_x, end_y all required for drag"
                pyautogui.moveTo(x, y, duration=0.2)
                pyautogui.dragTo(end_x, end_y, duration=0.4, button="left")
                return f"Dragged ({x},{y}) → ({end_x},{end_y})"
            return f"[Error] Unknown action '{action}'"

        return await asyncio.get_event_loop().run_in_executor(None, _run)


# ── Open App ───────────────────────────────────────────────────────────────────

# name aliases → binary/command
_APP_ALIASES: dict[str, list[str]] = {
    "terminal":      ["gnome-terminal", "konsole", "xfce4-terminal", "xterm", "x-terminal-emulator"],
    "files":         ["nautilus", "thunar", "dolphin", "nemo"],
    "file manager":  ["nautilus", "thunar", "dolphin", "nemo"],
    "browser":       ["xdg-open", "firefox", "google-chrome", "chromium-browser", "chromium"],
    "chrome":        ["google-chrome", "chromium-browser", "chromium"],
    "firefox":       ["firefox"],
    "vscode":        ["code"],
    "vs code":       ["code"],
    "code":          ["code"],
    "spotify":       ["spotify", "flatpak run com.spotify.Client"],
    "discord":       ["discord", "flatpak run com.discordapp.Discord"],
    "slack":         ["slack", "flatpak run com.slack.Slack"],
    "telegram":      ["telegram-desktop", "flatpak run org.telegram.desktop"],
    "calculator":    ["gnome-calculator", "kcalc", "xcalc"],
    "settings":      ["gnome-control-center", "systemsettings5"],
    "text editor":   ["gedit", "kate", "mousepad", "xed"],
    "vlc":           ["vlc"],
    "steam":         ["steam"],
    "obs":           ["obs"],
}


class OpenAppTool(BaseTool):
    name = "open_app"
    description = (
        "Open an application by name (e.g. 'firefox', 'terminal', 'vscode', 'spotify'), "
        "or open a file path or URL. Tries multiple known binary names automatically."
    )
    parameters = {
        "app": {
            "type": "string",
            "description": "App name, file path, or URL to open.",
        },
        "args": {
            "type": "array",
            "description": "Optional extra arguments.",
        },
    }
    required = ["app"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, app: str, args: list[str] | None = None) -> str:
        def _launch() -> str:
            env = _display_env()
            extra = args or []
            app_lower = app.lower().strip()

            # URLs / file paths → xdg-open
            if app_lower.startswith(("http://", "https://", "/", "~/", ".")):
                try:
                    subprocess.Popen(
                        ["xdg-open", app] + extra,
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return f"Opened '{app}' in default handler"
                except Exception as e:
                    return f"[Error] xdg-open failed: {e}"

            # Try alias list first
            candidates: list[list[str]] = []
            for key, cmds in _APP_ALIASES.items():
                if key in app_lower or app_lower in key:
                    for cmd in cmds:
                        candidates.append(cmd.split() + extra)

            # Also try the raw app name
            candidates.append([app] + extra)
            candidates.append(["xdg-open", app] + extra)

            last_err = ""
            for cmd in candidates:
                binary = cmd[0]
                # Quick existence check
                which = subprocess.run(["which", binary], capture_output=True, text=True)
                if which.returncode != 0:
                    continue
                try:
                    subprocess.Popen(
                        cmd, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return f"Launched {' '.join(cmd)}"
                except Exception as e:
                    last_err = str(e)

            # Flatpak search as last resort
            fp = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True, text=True,
            )
            if fp.returncode == 0:
                for line in fp.stdout.splitlines():
                    if app_lower in line.lower():
                        try:
                            subprocess.Popen(
                                ["flatpak", "run", line.strip()] + extra,
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True,
                            )
                            return f"Launched via Flatpak: {line.strip()}"
                        except Exception as e:
                            last_err = str(e)

            return (
                f"[Error] Could not find or launch '{app}'. "
                f"Is it installed? Last error: {last_err or 'binary not found in PATH'}. "
                f"Try installing it or provide the exact binary name."
            )

        return await asyncio.get_event_loop().run_in_executor(None, _launch)
