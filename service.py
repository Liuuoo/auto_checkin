"""共用服务层 - 配置、自启、日志、通知、单实例、托盘图标"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from PIL import Image, ImageDraw

from config_manager import load_config, save_config

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_NAME = "GitHubDailyCheckin"
APP_TITLE = "GitHub 每日签到"
LOG_DIR = os.path.join(os.path.expanduser("~"), ".github_checkin")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

TRAY_COLOR = "#1f6feb"

try:
    import winreg
    _REG_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
except ImportError:
    winreg = None
    _REG_RUN = ""


# ── 服务配置 ─────────────────────────────────────────
_DEFAULT_SERVICE = {"schedule_time": "09:00", "auto_start": False}


def get_service_config():
    config = load_config() or {}
    svc = config.get("service", {})
    for k, v in _DEFAULT_SERVICE.items():
        svc.setdefault(k, v)
    return svc


def save_service_config(svc):
    config = load_config() or {}
    config["service"] = svc
    save_config(config)


# ── 开机自启 ─────────────────────────────────────────
def is_auto_start():
    if not winreg:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_RUN, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False


def set_auto_start(enable):
    if not winreg:
        return
    if enable:
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}"'
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            exe = pythonw if os.path.exists(pythonw) else sys.executable
            cmd = f'"{exe}" "{os.path.join(BASE_DIR, "main.py")}"'
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_RUN, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
        except OSError:
            pass
    else:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_RUN, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
        except (FileNotFoundError, OSError):
            pass


# ── 托盘图标 ─────────────────────────────────────────
def create_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, 60, 60], radius=14, fill=TRAY_COLOR)
    d.line([(18, 34), (28, 46), (46, 20)], fill="white", width=5)
    return img


# ── 日志 ─────────────────────────────────────────────
_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("checkin")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    _logger = logger
    return logger


class LoggerStream:
    """把 print 的输出转发到 logger.info，供 run_checkin 复用"""

    def __init__(self, level=logging.INFO):
        self._level = level
        self._buf = ""

    def write(self, s):
        if not s:
            return
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                get_logger().log(self._level, line.rstrip())

    def flush(self):
        if self._buf.strip():
            get_logger().log(self._level, self._buf.rstrip())
        self._buf = ""


# ── 通知 ─────────────────────────────────────────────
def notify(icon, title, message):
    """pystray 气泡通知；icon 可为 None（用于测试）"""
    if icon is None:
        return
    try:
        icon.notify(message, title)
    except Exception:
        get_logger().exception("通知发送失败")


# ── 单实例 ───────────────────────────────────────────
class SingleInstance:
    """基于 Windows 命名互斥量的单实例锁，非 Windows 平台退化为永远允许启动"""

    def __init__(self, name=f"Global\\{APP_NAME}_Mutex"):
        self.name = name
        self.handle = None
        self._acquired = False

    def acquire(self):
        if os.name != "nt":
            self._acquired = True
            return True
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            ERROR_ALREADY_EXISTS = 183
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                return False
            self._acquired = True
            return True
        except Exception:
            get_logger().exception("单实例锁获取失败")
            self._acquired = True
            return True

    def release(self):
        if self.handle and os.name == "nt":
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
        self._acquired = False
