"""Real Input Testing Utility for Unreal Engine games and editor windows.
Delivers genuine OS-level mouse and keyboard input through the real Windows message pump,
Slate input routing, and Unreal input subsystem.

Zero mocks, zero simulators, zero synthetic state injection.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import time
import logging
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger("gameforge.real_input")

# Win32 Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004

SW_RESTORE = 9
SW_SHOW = 5

# Common Virtual Key Codes
VK_CODES = {
    "W": 0x57,
    "A": 0x41,
    "S": 0x53,
    "D": 0x44,
    "R": 0x52,
    "E": 0x45,
    "TAB": 0x09,
    "SPACE": 0x20,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "ESCAPE": 0x1B,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
}

# Structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def find_windows_for_pid(pid: int) -> List[int]:
    """Finds all visible top-level HWNDs belonging to a process ID."""
    hwnds = []

    def enum_proc(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            lpdw_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_pid))
            if lpdw_pid.value == pid:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    return hwnds


def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_game_window_for_pid(pid: int) -> Optional[int]:
    """The process's Unreal game viewport window (class 'UnrealWindow'), never its log console."""
    for hwnd in find_windows_for_pid(pid):
        if get_window_class(hwnd) == "UnrealWindow":
            return hwnd
    return None


def find_window_by_title_contains(substring: str) -> Optional[int]:
    """Finds the first visible window whose title contains the substring."""
    result = None

    def enum_proc(hwnd, lparam):
        nonlocal result
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if substring.lower() in buf.value.lower():
                    result = hwnd
                    return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    return result


def get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    """Returns (left, top, right, bottom) of window."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def get_client_rect(hwnd: int) -> Tuple[int, int, int, int]:
    """Returns (left, top, right, bottom) in screen coordinates of the client area."""
    pt_topleft = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt_topleft))
    client_rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
    width = client_rect.right - client_rect.left
    height = client_rect.bottom - client_rect.top
    return pt_topleft.x, pt_topleft.y, pt_topleft.x + width, pt_topleft.y + height


def focus_window(hwnd: int) -> bool:
    """Brings window to foreground, unminimizes if necessary, and activates keyboard focus."""
    if not user32.IsWindow(hwnd):
        return False

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)

    fore_hwnd = user32.GetForegroundWindow()
    fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()

    if fore_thread != cur_thread:
        user32.AttachThreadInput(cur_thread, fore_thread, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(cur_thread, fore_thread, False)
    else:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

    user32.SetActiveWindow(hwnd)
    user32.SetFocus(hwnd)
    time.sleep(0.15)
    # Windows may refuse the foreground change; report what actually happened.
    return is_foreground(hwnd)


def is_foreground(hwnd: int) -> bool:
    """True only when hwnd itself is the foreground window, i.e. would receive SendInput.

    A same-process match is not enough: a Development game started with -log owns a console
    window too, and input sent while that console is foreground never reaches the game.
    """
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


class NotForegroundError(RuntimeError):
    """Raised instead of sending input: SendInput goes to the foreground window, which is not the target."""


def send_mouse_move(screen_x: int, screen_y: int):
    """Moves mouse cursor to absolute screen coordinates using Windows SendInput."""
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    # Absolute coordinates in SendInput range 0..65535
    norm_x = int(screen_x * 65536.0 / screen_w)
    norm_y = int(screen_y * 65536.0 / screen_h)

    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = norm_x
    inp.union.mi.dy = norm_y
    inp.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def send_mouse_click(screen_x: int, screen_y: int, button: str = "left", hold_duration_s: float = 0.05):
    """Moves mouse to absolute coordinates and sends genuine button down and up events."""
    send_mouse_move(screen_x, screen_y)
    time.sleep(0.05)

    down_flag = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
    up_flag = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP

    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    norm_x = int(screen_x * 65536.0 / screen_w)
    norm_y = int(screen_y * 65536.0 / screen_h)

    inp_down = INPUT()
    inp_down.type = INPUT_MOUSE
    inp_down.union.mi.dx = norm_x
    inp_down.union.mi.dy = norm_y
    inp_down.union.mi.dwFlags = down_flag | MOUSEEVENTF_ABSOLUTE
    user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))

    time.sleep(hold_duration_s)

    inp_up = INPUT()
    inp_up.type = INPUT_MOUSE
    inp_up.union.mi.dx = norm_x
    inp_up.union.mi.dy = norm_y
    inp_up.union.mi.dwFlags = up_flag | MOUSEEVENTF_ABSOLUTE
    user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))


def send_key_down(key: str):
    """Sends a genuine key-down event."""
    vk = VK_CODES.get(key.upper())
    if vk is None:
        raise ValueError(f"Unsupported key: {key}")
    scan = user32.MapVirtualKeyW(vk, 0)
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = scan
    inp.union.ki.dwFlags = 0
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def send_key_up(key: str):
    """Sends a genuine key-up event."""
    vk = VK_CODES.get(key.upper())
    if vk is None:
        raise ValueError(f"Unsupported key: {key}")
    scan = user32.MapVirtualKeyW(vk, 0)
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = scan
    inp.union.ki.dwFlags = KEYEVENTF_KEYUP
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def send_key_tap(key: str, hold_duration_s: float = 0.08):
    """Sends a key-down followed by a key-up after hold_duration_s."""
    send_key_down(key)
    time.sleep(hold_duration_s)
    send_key_up(key)


class RealInputSession:
    """Manages an active real-input session directed at an actual focused window."""

    def __init__(self, hwnd: int, target_name: str = ""):
        self.hwnd = hwnd
        self.target_name = target_name or get_window_title(hwnd)
        self.actions_log: List[Dict[str, Any]] = []

    def focus(self) -> bool:
        ok = focus_window(self.hwnd)
        self._record("focus", {"ok": ok, "hwnd": self.hwnd, "title": self.target_name})
        return ok

    def _require_foreground(self) -> None:
        """Never inject input unless the target window will receive it (it would land in another app)."""
        if not self.focus():
            self._record("input_refused", {"reason": "target window is not foreground"})
            raise NotForegroundError(f"'{self.target_name}' (HWND 0x{self.hwnd:X}) is not the foreground window; input not sent")

    def get_client_geometry(self) -> Dict[str, int]:
        l, t, r, b = get_client_rect(self.hwnd)
        return {"left": l, "top": t, "right": r, "bottom": b, "width": r - l, "height": b - t}

    def client_to_screen(self, rel_x_fraction: float, rel_y_fraction: float) -> Tuple[int, int]:
        geom = self.get_client_geometry()
        px = int(geom["left"] + geom["width"] * rel_x_fraction)
        py = int(geom["top"] + geom["height"] * rel_y_fraction)
        return px, py

    def click_fraction(self, rel_x_fraction: float, rel_y_fraction: float, button: str = "left", hold_s: float = 0.06):
        self._require_foreground()
        sx, sy = self.client_to_screen(rel_x_fraction, rel_y_fraction)
        send_mouse_click(sx, sy, button=button, hold_duration_s=hold_s)
        self._record("mouse_click", {"screen_x": sx, "screen_y": sy, "rel_x": rel_x_fraction, "rel_y": rel_y_fraction, "button": button})

    def move_mouse_fraction(self, rel_x_fraction: float, rel_y_fraction: float):
        self._require_foreground()
        sx, sy = self.client_to_screen(rel_x_fraction, rel_y_fraction)
        send_mouse_move(sx, sy)
        self._record("mouse_move", {"screen_x": sx, "screen_y": sy, "rel_x": rel_x_fraction, "rel_y": rel_y_fraction})

    def hold_key(self, key: str, duration_s: float):
        self._require_foreground()
        send_key_down(key)
        self._record("key_down", {"key": key})
        time.sleep(duration_s)
        send_key_up(key)
        self._record("key_up", {"key": key, "held_duration_s": duration_s})

    def tap_key(self, key: str, hold_s: float = 0.08):
        self._require_foreground()
        send_key_tap(key, hold_duration_s=hold_s)
        self._record("key_tap", {"key": key, "hold_s": hold_s})

    def _record(self, action_type: str, details: Dict[str, Any]):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "action": action_type,
            "target": self.target_name,
            **details,
        }
        self.actions_log.append(entry)
