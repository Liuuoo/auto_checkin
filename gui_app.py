"""GitHub 每日签到 - 现代化 GUI 桌面应用 (CustomTkinter)"""

import os
import sys
import threading
import time
import traceback
import re
import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk
import schedule
import pystray
from PIL import Image, ImageDraw, ImageFont

from config_manager import (
    DEFAULT_PROVIDERS, load_config, save_config,
    load_config_history, add_ai_profile, add_github_profile,
)
from content_generator import get_topic_names
from ai_client import AIClient
from github_manager import GitHubManager
from main import run_checkin

# ── 路径 ─────────────────────────────────────────────
if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

APP_NAME = "GitHubDailyCheckin"

try:
    import winreg
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
except ImportError:
    winreg = None
    REG_PATH = ""

# ── GitHub 现代风主题 (双色态 [Light, Dark]) ─────────
GH_THEME = {
    "bg":           ("#f6f8fa", "#0d1117"),
    "sidebar":      ("#ffffff", "#161b22"),
    "card":         ("#ffffff", "#161b22"),
    "card_hover":   ("#f3f4f6", "#21262d"),
    "primary":      ("#1f6feb", "#1f6feb"),       # GitHub Blue
    "primary_hover":("#388bfd", "#388bfd"),
    "success":      ("#238636", "#238636"),       # GitHub Green
    "success_hover":("#2ea043", "#2ea043"),
    "warning":      ("#d29922", "#d29922"),       # GitHub Yellow
    "danger":       ("#da3633", "#da3633"),       # GitHub Red
    "text":         ("#24292f", "#c9d1d9"),
    "text_dim":     ("#57606a", "#8b949e"),
    "border":       ("#d0d7de", "#30363d"),
    "input_bg":     ("#f6f8fa", "#0d1117"),
    "log_bg":       ("#f6f8fa", "#010409"),
    "log_fg":       ("#24292f", "#e6edf3"),
    "sidebar_sel":  ("#f3f4f6", "#21262d"),
}

FONT_FAMILY = "Microsoft YaHei UI"


# ── stdout 重定向 ────────────────────────────────────
class _StdoutRedirector:
    def __init__(self, callback):
        self._cb = callback

    def write(self, s):
        if s and s.strip():
            self._cb(s.strip())

    def flush(self):
        pass


# ── Markdown Textbox ────────────────────────────────
class MarkdownTextbox(ctk.CTkTextbox):
    """支持基础 Markdown 语法高亮的文本框"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.font_base = (FONT_FAMILY, 14)
        self.font_bold = (FONT_FAMILY, 14, "bold")
        self.font_h1 = (FONT_FAMILY, 22, "bold")
        self.font_h2 = (FONT_FAMILY, 19, "bold")
        self.font_h3 = (FONT_FAMILY, 16, "bold")
        self.font_code = ("Consolas", 13)
        self.code_bg = ("#eef1f5", "#161b22")

        # 优化渲染性能
        self._textbox.configure(blockcursor=False, insertwidth=2)

    def set_markdown(self, text):
        self.configure(state="normal")
        self.delete("1.0", "end")

        mode = ctk.get_appearance_mode()
        bg = self.code_bg[1] if mode == "Dark" else self.code_bg[0]
        quote_fg = GH_THEME["text_dim"][1] if mode == "Dark" else GH_THEME["text_dim"][0]

        self.tag_config("code", font=self.font_code, background=bg, lmargin1=10, lmargin2=10)
        self.tag_config("quote", font=(FONT_FAMILY, 14, "italic"), foreground=quote_fg, lmargin1=15, lmargin2=15)
        self.tag_config("bold", font=self.font_bold)
        self.tag_config("h1", font=self.font_h1, spacing1=12, spacing3=8)
        self.tag_config("h2", font=self.font_h2, spacing1=10, spacing3=6)
        self.tag_config("h3", font=self.font_h3, spacing1=8, spacing3=4)

        lines = text.split("\n")
        in_code_block = False

        for line in lines:
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                self.insert("end", line + "\n", "code")
                continue

            if line.startswith("# "):
                self.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                self.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("### "):
                self.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("> "):
                self.insert("end", line + "\n", "quote")
            else:
                # 简单处理 inline bold: **text**
                parts = re.split(r'(\*\*.*?\*\*)', line)
                for part in parts:
                    if part.startswith("**") and part.endswith("**"):
                        self.insert("end", part[2:-2], "bold")
                    elif part:
                        self.insert("end", part)
                self.insert("end", "\n")

        self.configure(state="disabled")
        # 强制刷新显示
        self.update_idletasks()


# ── 托盘图标 ─────────────────────────────────────────
def _create_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, 60, 60], radius=14, fill=GH_THEME["primary"][0])
    d.line([(18, 34), (28, 46), (46, 20)], fill="white", width=5)
    return img


# ── 自动启动 ─────────────────────────────────────────
def _is_auto_start():
    if not winreg:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False


def _set_auto_start(enable, silent=False):
    if not winreg:
        return
    if enable:
        if getattr(sys, "frozen", False):
            parts = [f'"{sys.executable}"']
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            parts = [f'"{pythonw}"', f'"{os.path.join(SCRIPT_DIR, "gui_app.py")}"']
        if silent:
            parts.append("--minimized")
        cmd = " ".join(parts)
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
        except OSError:
            pass
    else:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
        except (FileNotFoundError, OSError):
            pass


def _get_service_config():
    config = load_config()
    defaults = {"port": 10025, "auto_start": False, "schedule_time": "09:00",
                "minimize_to_tray": True, "silent_start": True}
    if not config:
        return defaults
    svc = config.get("service", {})
    for k, v in defaults.items():
        svc.setdefault(k, v)
    return svc


def _save_service_config(svc):
    config = load_config() or {}
    config["service"] = svc
    save_config(config)


# ══════════════════════════════════════════════════════
#  响应式布局管理器
# ══════════════════════════════════════════════════════
class ResponsiveLayoutManager:
    """响应式布局管理器 - 处理窗口大小变化和布局切换"""

    BREAKPOINTS = {
        "mobile": 600,   # 小屏：隐藏侧边栏，单列
        "tablet": 900,   # 中屏：显示侧边栏，单列
        "desktop": 1200  # 大屏：侧边栏 + 可能多列
    }

    def __init__(self, app):
        self.app = app
        self.current_breakpoint = "desktop"
        self.sidebar_visible = True
        self.columns = 1  # 当前卡片列数

    def on_window_resize(self, width):
        """窗口宽度变化时调用"""
        new_breakpoint = self._get_breakpoint(width)

        if new_breakpoint != self.current_breakpoint:
            self.current_breakpoint = new_breakpoint
            self._apply_layout()

    def _get_breakpoint(self, width):
        if width < self.BREAKPOINTS["mobile"]:
            return "mobile"
        elif width < self.BREAKPOINTS["tablet"]:
            return "tablet"
        else:
            return "desktop"

    def _apply_layout(self):
        """根据断点应用布局"""
        if self.current_breakpoint == "mobile":
            self._hide_sidebar()
            self.columns = 1
        elif self.current_breakpoint == "tablet":
            self._show_sidebar()
            self.columns = 1
        else:  # desktop
            self._show_sidebar()
            self.columns = 1  # 可根据需要改为2

        # 通知配置页面重新布局卡片
        if hasattr(self.app, '_config_card_container'):
            self.app._relayout_cards(self.app._config_card_container, self.columns)

    def _hide_sidebar(self):
        if self.sidebar_visible:
            self.app._sidebar.grid_remove()
            self.app.grid_columnconfigure(0, minsize=0, weight=0)
            self.sidebar_visible = False

    def _show_sidebar(self):
        if not self.sidebar_visible:
            self.app._sidebar.grid()
            self.app.grid_columnconfigure(0, minsize=220, weight=0)
            self.sidebar_visible = True


# ══════════════════════════════════════════════════════
#  主应用
# ══════════════════════════════════════════════════════
class CheckinApp(ctk.CTk):

    def __init__(self, start_minimized=False):
        super().__init__()

        # DPI 适配
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        
        # 默认使用系统主题
        ctk.set_appearance_mode("system")
        
        self.title("GitHub 每日签到")
        self.geometry("1200x850")
        self.minsize(1000, 700)
        self.configure(fg_color=GH_THEME["bg"])

        # ── 状态 ──
        self.is_running = False
        self.last_checkin = None
        self.last_result = None
        self.tray_icon = None
        self._start_minimized = start_minimized
        self._current_page = None

        # ── 配置主窗口 grid ──
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=220)  # 侧边栏列
        self.grid_columnconfigure(1, weight=1)  # 内容列

        # ── 构建 UI ──
        self._build_sidebar()
        self._content = ctk.CTkFrame(self, fg_color=GH_THEME["bg"], corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")

        self._pages = {}
        self._build_checkin_page()
        self._build_config_page()
        self._build_settings_page()
        self._show_page("checkin")

        # ── 响应式管理器 ──
        self.responsive_mgr = ResponsiveLayoutManager(self)
        self._resize_timer = None
        self.bind("<Configure>", self._on_window_configure)

        # ── 定时 & 托盘 ──
        self._setup_scheduler()
        self._setup_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if start_minimized:
            self.after(100, self._hide_to_tray)

    def _on_window_configure(self, event):
        """窗口大小变化处理（带防抖）"""
        if event.widget == self:
            if self._resize_timer:
                self.after_cancel(self._resize_timer)

            self._resize_timer = self.after(200,
                lambda: self.responsive_mgr.on_window_resize(event.width))

    # ──────────────────────────────────────────────────
    #  侧边栏
    # ──────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=GH_THEME["sidebar"], corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")  # 改用 grid
        sb.grid_propagate(False)  # 防止自动调整大小
        self._sidebar = sb  # 保存引用供响应式管理器使用

        # Logo
        logo_frame = ctk.CTkFrame(sb, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(32, 16))
        ctk.CTkLabel(logo_frame, text="✦", font=(FONT_FAMILY, 30),
                     text_color=GH_THEME["primary"]).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(logo_frame, text="GitHub 签到",
                     font=(FONT_FAMILY, 20, "bold"),
                     text_color=GH_THEME["text"]).pack(side="left")

        ctk.CTkFrame(sb, height=1, fg_color=GH_THEME["border"]).pack(fill="x", padx=16, pady=20)

        # 导航按钮
        self._nav_buttons = {}
        nav_items = [
            ("checkin", "🏠", "签 到"),
            ("config",  "⚙️", "配 置"),
            ("settings","🔧", "设 置"),
        ]
        for key, icon, label in nav_items:
            btn = ctk.CTkButton(
                sb, text=f"  {icon}   {label}", anchor="w",
                font=(FONT_FAMILY, 15, "bold"), height=46,
                fg_color="transparent", text_color=GH_THEME["text_dim"],
                hover_color=GH_THEME["card_hover"], corner_radius=8,
                command=lambda k=key: self._show_page(k),
            )
            btn.pack(fill="x", padx=16, pady=4)
            self._nav_buttons[key] = btn

        # 底部 外观模式选择
        mode_frame = ctk.CTkFrame(sb, fg_color="transparent")
        mode_frame.pack(side="bottom", fill="x", padx=16, pady=24)
        ctk.CTkLabel(mode_frame, text="外观模式", font=(FONT_FAMILY, 13), 
                     text_color=GH_THEME["text_dim"]).pack(anchor="w", pady=(0, 6))
        self._appearance_combo = ctk.CTkComboBox(
            mode_frame, values=["跟随系统", "浅色 (Light)", "深色 (Dark)"],
            font=(FONT_FAMILY, 13), height=36,
            fg_color=GH_THEME["input_bg"], border_color=GH_THEME["border"],
            button_color=GH_THEME["primary"], dropdown_fg_color=GH_THEME["card"],
            state="readonly", command=self._change_appearance_mode
        )
        self._appearance_combo.pack(fill="x")
        self._appearance_combo.set("跟随系统")

    def _change_appearance_mode(self, new_mode: str):
        if new_mode == "浅色 (Light)":
            ctk.set_appearance_mode("Light")
        elif new_mode == "深色 (Dark)":
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("System")
            
        # 刷新一下文章预览的颜色（因为背景需要代码动态重算）
        text = self._preview_box.get("1.0", "end").strip()
        if text:
            self._set_preview(text)

    def _show_page(self, name):
        if self._current_page == name:
            return
        self._current_page = name
        for k, btn in self._nav_buttons.items():
            if k == name:
                # 侧边栏选中态，仍然用稍微区分背景和高亮文字
                btn.configure(fg_color=GH_THEME["sidebar_sel"], text_color=GH_THEME["primary"])
            else:
                btn.configure(fg_color="transparent", text_color=GH_THEME["text_dim"])
        for child in self._content.winfo_children():
            child.pack_forget()
        self._pages[name].pack(fill="both", expand=True)

    # ──────────────────────────────────────────────────
    #  签到页
    # ──────────────────────────────────────────────────
    def _build_checkin_page(self):
        page = ctk.CTkFrame(self._content, fg_color=GH_THEME["bg"])
        self._pages["checkin"] = page

        # 标题区域
        ctk.CTkLabel(page, text="签到中心", font=(FONT_FAMILY, 28, "bold"),
                     text_color=GH_THEME["text"]).pack(anchor="w", padx=32, pady=(28, 8))
        ctk.CTkLabel(page, text="自动生成技术文档并推送至您的 GitHub 仓库。",
                     font=(FONT_FAMILY, 14), text_color=GH_THEME["text_dim"]
                     ).pack(anchor="w", padx=32, pady=(0, 20))

        # 工作流控制区
        ctrl_card = ctk.CTkFrame(page, fg_color=GH_THEME["card"], corner_radius=12, border_width=1, border_color=GH_THEME["border"])
        ctrl_card.pack(fill="x", padx=32, pady=(0, 20))

        # 顶部 状态
        status_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        status_row.pack(fill="x", padx=24, pady=(20, 16))
        self._status_dot = ctk.CTkLabel(status_row, text="● 服务运行中",
                                         font=(FONT_FAMILY, 14, "bold"), text_color=GH_THEME["success"])
        self._status_dot.pack(side="left")
        
        self._lbl_next = ctk.CTkLabel(status_row, text="下次签到：—", font=(FONT_FAMILY, 13), text_color=GH_THEME["text_dim"])
        self._lbl_next.pack(side="right")
        self._lbl_last = ctk.CTkLabel(status_row, text="上次签到：尚未", font=(FONT_FAMILY, 13), text_color=GH_THEME["text_dim"])
        self._lbl_last.pack(side="right", padx=(0, 32))

        # 线条
        ctk.CTkFrame(ctrl_card, height=1, fg_color=GH_THEME["border"]).pack(fill="x")

        # 底部 选项与按钮
        action_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        action_row.pack(fill="x", padx=24, pady=20)

        ctk.CTkLabel(action_row, text="📅  主题", font=(FONT_FAMILY, 14, "bold"), text_color=GH_THEME["text"]).pack(side="left", padx=(0, 12))
        topics = ["随机"] + get_topic_names()
        self._topic_var = ctk.StringVar(value="随机")
        ctk.CTkComboBox(action_row, variable=self._topic_var, values=topics,
                        width=180, height=38, font=(FONT_FAMILY, 14),
                        fg_color=GH_THEME["input_bg"], border_color=GH_THEME["border"],
                        button_color=GH_THEME["primary"], dropdown_fg_color=GH_THEME["card"],
                        state="readonly").pack(side="left", padx=(0, 32))

        ctk.CTkLabel(action_row, text="🔢  数量", font=(FONT_FAMILY, 14, "bold"), text_color=GH_THEME["text"]).pack(side="left", padx=(0, 12))
        self._count_var = ctk.StringVar(value="1")
        ctk.CTkEntry(action_row, textvariable=self._count_var, width=70, height=38,
                     font=(FONT_FAMILY, 14), fg_color=GH_THEME["input_bg"],
                     border_color=GH_THEME["border"]).pack(side="left")

        # 按钮始终放在右边
        ctk.CTkButton(action_row, text="▶  立即签到", font=(FONT_FAMILY, 14, "bold"),
                      fg_color=GH_THEME["success"], hover_color=GH_THEME["success_hover"],
                      corner_radius=8, height=40, width=140,
                      command=self._do_checkin).pack(side="right")
        ctk.CTkButton(action_row, text="👁  仅预览", font=(FONT_FAMILY, 14, "bold"),
                      fg_color=GH_THEME["card_hover"], hover_color=GH_THEME["border"],
                      text_color=GH_THEME["text"], border_width=1, border_color=GH_THEME["border"],
                      corner_radius=8, height=40, width=110,
                      command=self._do_preview).pack(side="right", padx=16)

        # ── 下方控制面板 (日志/预览框) ──
        bottom_container = ctk.CTkFrame(page, fg_color="transparent")
        bottom_container.pack(fill="both", expand=True, padx=32, pady=(0, 24))

        # 运行日志
        log_frame = ctk.CTkFrame(bottom_container, fg_color=GH_THEME["card"], corner_radius=12, border_width=1, border_color=GH_THEME["border"])
        log_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        ctk.CTkLabel(log_frame, text="📋  运行日志", font=(FONT_FAMILY, 15, "bold"),
                     text_color=GH_THEME["text"]).pack(anchor="w", padx=20, pady=(16, 8))

        self._log_box = ctk.CTkTextbox(
            log_frame, font=("Consolas", 13), wrap="word",
            fg_color=GH_THEME["log_bg"], text_color=GH_THEME["log_fg"],
            border_width=1, border_color=GH_THEME["border"], corner_radius=12, state="disabled",
        )
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # 文章预览
        preview_frame = ctk.CTkFrame(bottom_container, fg_color=GH_THEME["card"], corner_radius=12, border_width=1, border_color=GH_THEME["border"])
        preview_frame.pack(side="right", fill="both", expand=True, padx=(8, 0))

        ctk.CTkLabel(preview_frame, text="📄  文章预览", font=(FONT_FAMILY, 15, "bold"),
                     text_color=GH_THEME["text"]).pack(anchor="w", padx=20, pady=(16, 8))

        self._preview_box = MarkdownTextbox(
            preview_frame, wrap="word",
            fg_color=GH_THEME["bg"], text_color=GH_THEME["text"],
            border_width=1, border_color=GH_THEME["border"], corner_radius=12, state="disabled",
        )
        self._preview_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._log("✔️  应用已启动并就绪")
        self._update_next_label()

    # ──────────────────────────────────────────────────
    #  配置页
    # ──────────────────────────────────────────────────
    def _build_config_page(self):
        page = ctk.CTkScrollableFrame(self._content, fg_color=GH_THEME["bg"],
                                      scrollbar_button_color=GH_THEME["primary"],
                                      scrollbar_button_hover_color=GH_THEME["primary_hover"])
        self._pages["config"] = page

        # 优化滚动性能：绑定鼠标滚轮事件
        def _on_mousewheel(event):
            page._parent_canvas.yview_scroll(int(-1 * (event.delta / 60)), "units")
        page._parent_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        config = load_config() or {}
        ai_cfg = config.get("ai", {})
        gh_cfg = config.get("github", {})

        ctk.CTkLabel(page, text="模型与仓库配置", font=(FONT_FAMILY, 28, "bold"),
                     text_color=GH_THEME["text"]).pack(anchor="w", padx=32, pady=(20, 12))

        # 创建卡片容器（用于 grid 布局卡片）
        self._config_card_container = ctk.CTkFrame(page, fg_color="transparent")
        self._config_card_container.pack(fill="both", expand=True, padx=32)

        # 全局输入框对齐参数
        lbl_width = 120

        # ── AI 配置 ──
        ai_card = self._card(self._config_card_container, "🤖  AI 模型配置")

        history = load_config_history()
        ai_names = [p["name"] for p in history.get("ai_profiles", [])]
        self._ai_hist_var = ctk.StringVar(value="")
        self._ai_hist_combo = self._add_field(ai_card, "历史配置", combo=True, 
                                              var=self._ai_hist_var, 
                                              values=ai_names if ai_names else ["（无历史记录）"], 
                                              label_width=lbl_width,
                                              cb=self._on_ai_hist_select)

        self._provider_var = ctk.StringVar(value=ai_cfg.get("provider", "SiliconFlow"))
        self._add_field(ai_card, "服务商", combo=True,
                        var=self._provider_var,
                        values=[v["name"] for v in DEFAULT_PROVIDERS.values()],
                        label_width=lbl_width,
                        cb=self._on_provider_change)

        self._base_url_var = ctk.StringVar(value=ai_cfg.get("base_url", ""))
        self._add_field(ai_card, "API 地址", var=self._base_url_var, label_width=lbl_width)

        self._model_var = ctk.StringVar(value=ai_cfg.get("model", ""))
        self._add_field(ai_card, "模型名称", var=self._model_var, label_width=lbl_width)

        self._apikey_var = ctk.StringVar(value=ai_cfg.get("api_key", ""))
        self._add_field(ai_card, "API Key", var=self._apikey_var, show="*", label_width=lbl_width)

        btn_row = ctk.CTkFrame(ai_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=4)
        # 补齐 label_width 以对齐按钮
        ctk.CTkFrame(btn_row, width=lbl_width, fg_color="transparent").pack(side="left", padx=0, pady=0)

        ctk.CTkButton(btn_row, text="🔗  测试 AI 连接", width=160, height=38,
                      font=(FONT_FAMILY, 14, "bold"),
                      fg_color=GH_THEME["card_hover"], hover_color=GH_THEME["border"],
                      text_color=GH_THEME["text"], border_width=1, border_color=GH_THEME["border"],
                      corner_radius=8, command=self._test_ai).pack(side="left", padx=0, pady=0)
        self._ai_test_lbl = ctk.CTkLabel(btn_row, text="", font=(FONT_FAMILY, 13), text_color=GH_THEME["text_dim"])
        self._ai_test_lbl.pack(side="left", padx=(12, 0), pady=0)

        # ── GitHub 配置 ──
        gh_card = self._card(self._config_card_container, "🐙  GitHub 仓库配置")

        gh_names = [p["name"] for p in history.get("github_profiles", [])]
        self._gh_hist_var = ctk.StringVar(value="")
        self._gh_hist_combo = self._add_field(gh_card, "历史配置", combo=True,
                                                var=self._gh_hist_var,
                                                values=gh_names if gh_names else ["（无历史记录）"],
                                                label_width=lbl_width,
                                                cb=self._on_gh_hist_select)

        self._repo_url_var = ctk.StringVar(value=gh_cfg.get("repo_url", ""))
        self._add_field(gh_card, "仓库地址", var=self._repo_url_var, label_width=lbl_width)

        self._auth_var = ctk.StringVar(value=gh_cfg.get("auth_type", "ssh"))
        auth_row = ctk.CTkFrame(gh_card, fg_color="transparent")
        auth_row.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(auth_row, text="认证方式", font=(FONT_FAMILY, 14),
                     text_color=GH_THEME["text"], width=lbl_width, anchor="w").pack(side="left")
        ctk.CTkRadioButton(auth_row, text="SSH", variable=self._auth_var, value="ssh",
                           font=(FONT_FAMILY, 14), text_color=GH_THEME["text"],
                           fg_color=GH_THEME["primary"], hover_color=GH_THEME["primary_hover"],
                           command=self._on_auth_toggle).pack(side="left", padx=(0, 24))
        ctk.CTkRadioButton(auth_row, text="HTTPS + Token", variable=self._auth_var, value="https",
                           font=(FONT_FAMILY, 14), text_color=GH_THEME["text"],
                           fg_color=GH_THEME["primary"], hover_color=GH_THEME["primary_hover"],
                           command=self._on_auth_toggle).pack(side="left")

        # Token
        self._token_var = ctk.StringVar(value=gh_cfg.get("token", ""))
        self._token_frame = ctk.CTkFrame(gh_card, fg_color="transparent")
        self._add_field(self._token_frame, "Token", var=self._token_var, show="*", label_width=lbl_width, no_pack=True)
        if self._auth_var.get() == "https":
            self._token_frame.pack(fill="x", pady=(0, 0))

        self._local_dir_var = ctk.StringVar(value=gh_cfg.get("local_dir", os.path.join(SCRIPT_DIR, "repo")))
        dir_row = ctk.CTkFrame(gh_card, fg_color="transparent")
        dir_row.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(dir_row, text="本地目录", font=(FONT_FAMILY, 14),
                     text_color=GH_THEME["text"], width=lbl_width, anchor="w").pack(side="left")
        ctk.CTkEntry(dir_row, textvariable=self._local_dir_var, height=38,
                     font=(FONT_FAMILY, 14), fg_color=GH_THEME["input_bg"],
                     border_color=GH_THEME["border"]).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dir_row, text="📂 浏览", width=80, height=38, font=(FONT_FAMILY, 13),
                      fg_color=GH_THEME["card_hover"], hover_color=GH_THEME["border"],
                      text_color=GH_THEME["text"], border_width=1, border_color=GH_THEME["border"],
                      corner_radius=8, command=self._browse_dir).pack(side="left", padx=(8, 0))

        gh_btn_row = ctk.CTkFrame(gh_card, fg_color="transparent")
        gh_btn_row.pack(fill="x", padx=24, pady=4)
        ctk.CTkFrame(gh_btn_row, width=lbl_width, fg_color="transparent").pack(side="left", padx=0, pady=0)
        ctk.CTkButton(gh_btn_row, text="🔗  测试仓库连接", width=160, height=38,
                      font=(FONT_FAMILY, 14, "bold"),
                      fg_color=GH_THEME["card_hover"], hover_color=GH_THEME["border"],
                      text_color=GH_THEME["text"], border_width=1, border_color=GH_THEME["border"],
                      corner_radius=8, command=self._test_repo).pack(side="left", padx=0, pady=0)
        self._repo_test_lbl = ctk.CTkLabel(gh_btn_row, text="", font=(FONT_FAMILY, 13), text_color=GH_THEME["text_dim"])
        self._repo_test_lbl.pack(side="left", padx=(12, 0), pady=0)

        # 初始布局（默认单列）
        self._relayout_cards(self._config_card_container, 1)

        # 保存按钮
        ctk.CTkButton(page, text="💾  保存所有配置", height=44, width=220,
                      font=(FONT_FAMILY, 15, "bold"),
                      fg_color=GH_THEME["primary"], hover_color=GH_THEME["primary_hover"],
                      corner_radius=8, command=self._save_all_config
                      ).pack(anchor="w", padx=32, pady=(8, 20))

    # ──────────────────────────────────────────────────
    #  设置页
    # ──────────────────────────────────────────────────
    def _build_settings_page(self):
        page = ctk.CTkFrame(self._content, fg_color=GH_THEME["bg"])
        self._pages["settings"] = page

        svc = _get_service_config()

        ctk.CTkLabel(page, text="应用首选项", font=(FONT_FAMILY, 28, "bold"),
                     text_color=GH_THEME["text"]).pack(anchor="w", padx=32, pady=(28, 20))

        card = self._card(page, "⏰  服务与启动管理")
        lbl_width = 160

        # 签到时间
        time_row = ctk.CTkFrame(card, fg_color="transparent")
        time_row.pack(fill="x", padx=24, pady=10)
        ctk.CTkLabel(time_row, text="每日签到时间", font=(FONT_FAMILY, 14),
                     text_color=GH_THEME["text"], width=lbl_width, anchor="w").pack(side="left")
        self._time_var = ctk.StringVar(value=svc.get("schedule_time", "09:00"))
        ctk.CTkEntry(time_row, textvariable=self._time_var, width=100, height=38,
                     font=(FONT_FAMILY, 14), fg_color=GH_THEME["input_bg"],
                     border_color=GH_THEME["border"]).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(time_row, text="(格式: HH:MM)", font=(FONT_FAMILY, 13),
                     text_color=GH_THEME["text_dim"]).pack(side="left")

        # 端口
        port_row = ctk.CTkFrame(card, fg_color="transparent")
        port_row.pack(fill="x", padx=24, pady=10)
        ctk.CTkLabel(port_row, text="状态页端口", font=(FONT_FAMILY, 14),
                     text_color=GH_THEME["text"], width=lbl_width, anchor="w").pack(side="left")
        self._port_var = ctk.StringVar(value=str(svc.get("port", 10025)))
        ctk.CTkEntry(port_row, textvariable=self._port_var, width=100, height=38,
                     font=(FONT_FAMILY, 14), fg_color=GH_THEME["input_bg"],
                     border_color=GH_THEME["border"]).pack(side="left")

        # 开关选项
        self._auto_start_var = ctk.BooleanVar(value=_is_auto_start())
        self._switch(card, "开机自动启动", self._auto_start_var)

        self._silent_var = ctk.BooleanVar(value=svc.get("silent_start", True))
        self._switch(card, "启动时静默进入托盘", self._silent_var)

        self._minimize_var = ctk.BooleanVar(value=svc.get("minimize_to_tray", True))
        self._switch(card, "关闭窗口时最小化到托盘", self._minimize_var)

        ctk.CTkButton(page, text="💾  保存设置", height=44, width=180,
                      font=(FONT_FAMILY, 15, "bold"),
                      fg_color=GH_THEME["primary"], hover_color=GH_THEME["primary_hover"],
                      corner_radius=8, command=self._save_settings
                      ).pack(anchor="w", padx=32, pady=(16, 24))

    # ══════════════════════════════════════════════════
    #  UI 工具方法
    # ══════════════════════════════════════════════════
    def _card(self, parent, title):
        """创建卡片（不立即布局，等待统一布局）"""
        card = ctk.CTkFrame(parent, fg_color=GH_THEME["card"], corner_radius=12, border_width=1, border_color=GH_THEME["border"])

        # 卡片内部仍使用 pack
        ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 16, "bold"),
                     text_color=GH_THEME["text"]).pack(anchor="w", padx=24, pady=(12, 6))
        ctk.CTkFrame(card, height=1, fg_color=GH_THEME["border"]).pack(fill="x")

        # 将卡片添加到父容器的卡片列表
        if not hasattr(parent, '_cards'):
            parent._cards = []
        parent._cards.append(card)

        return card

    def _relayout_cards(self, parent, columns):
        """根据列数重新布局卡片（流式布局）"""
        if not hasattr(parent, '_cards'):
            return

        # 清除现有布局
        for card in parent._cards:
            card.grid_forget()

        # 配置列权重（uniform 确保列宽相等）
        for col in range(columns):
            parent.grid_columnconfigure(col, weight=1, uniform="card")

        # 清除多余列
        for col in range(columns, 5):
            parent.grid_columnconfigure(col, weight=0, uniform="")

        # 重新布局卡片
        for idx, card in enumerate(parent._cards):
            row = idx // columns
            col = idx % columns
            card.grid(row=row, column=col, sticky="ew",
                     padx=12, pady=8)

    def _add_field(self, parent, label, var=None, show=None, combo=False, values=None, cb=None, label_width=100, no_pack=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        if not no_pack:
            row.pack(fill="x", padx=24, pady=4)

        ctk.CTkLabel(row, text=label, font=(FONT_FAMILY, 14),
                     text_color=GH_THEME["text"], width=label_width, anchor="w").pack(side="left")
        if combo:
            w = ctk.CTkComboBox(row, variable=var, values=values or [],
                                height=38, font=(FONT_FAMILY, 14),
                                fg_color=GH_THEME["input_bg"], border_color=GH_THEME["border"],
                                button_color=GH_THEME["primary"], dropdown_fg_color=GH_THEME["card"],
                                dropdown_font=(FONT_FAMILY, 13),
                                command=cb, state="readonly")
            w.pack(side="left", fill="x", expand=True)
            return w
        else:
            kw = dict(textvariable=var, font=(FONT_FAMILY, 14), height=38,
                      fg_color=GH_THEME["input_bg"], border_color=GH_THEME["border"])
            if show:
                kw["show"] = show
            w = ctk.CTkEntry(row, **kw)
            w.pack(side="left", fill="x", expand=True)
            if no_pack:
                row.pack(fill="x", padx=24, pady=4)
            return w

    def _switch(self, parent, label, var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=10)
        ctk.CTkSwitch(row, variable=var, text=label,
                      font=(FONT_FAMILY, 14), text_color=GH_THEME["text"],
                      fg_color=GH_THEME["border"], progress_color=GH_THEME["primary"],
                      button_color=GH_THEME["card"]).pack(side="left")

    # ══════════════════════════════════════════════════
    #  日志 & 预览
    # ══════════════════════════════════════════════════
    def _log(self, msg):
        if not self.winfo_exists():
            return

        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            lines = msg.split("\n")
            self._log_box.configure(state="normal")
            for i, line in enumerate(lines):
                prefix = f"[{ts}]" if i == 0 else "        "
                self._log_box.insert("end", f"{prefix}  {line}\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
            # 强制刷新显示
            self._log_box.update_idletasks()

        self.after(0, _do)

    def _set_preview(self, text):
        if not self.winfo_exists():
            return
        def _do():
            self._preview_box.set_markdown(text)
        self.after(0, _do)

    # ══════════════════════════════════════════════════
    #  签到逻辑
    # ══════════════════════════════════════════════════
    def _do_checkin(self, dry_run=False):
        if self.is_running:
            self._log("⏳ 签到正在进行中，请稍候...")
            return

        topic = self._topic_var.get()
        topic_name = None if topic == "随机" else topic
        try:
            count = max(1, min(10, int(self._count_var.get())))
        except ValueError:
            count = 1

        def on_article(filename, content):
            self._set_preview(content)

        def worker():
            self.is_running = True
            self.after(0, self._update_status)
            mode = "预览" if dry_run else "签到"
            self._log(f"▶ 开始{mode} ({topic_name or '随机主题'} ×{count})…")

            old_stdout = sys.stdout
            sys.stdout = _StdoutRedirector(self._log)
            try:
                run_checkin(dry_run=dry_run, topic_name=topic_name,
                            count=count, on_article=on_article)
                self.last_checkin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_result = "成功"
                self._log(f"✅ {mode}完成！共 {count} 篇")
            except Exception as e:
                self._log(f"❌ 程序报错:\n{traceback.format_exc()}")
                self.last_checkin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_result = f"失败: {e}"
                self._log(f"❌ {mode}失败: {e}")
            finally:
                sys.stdout = old_stdout
                self.is_running = False
                self.after(0, self._update_status)
                self.after(0, self._update_next_label)

        threading.Thread(target=worker, daemon=True).start()

    def _do_preview(self):
        self._do_checkin(dry_run=True)

    def _update_status(self):
        if self.is_running:
            self._status_dot.configure(text="● 签到中…", text_color=GH_THEME["warning"])
        else:
            self._status_dot.configure(text="● 服务运行中", text_color=GH_THEME["success"])
        if self.last_checkin:
            self._lbl_last.configure(text=f"上次签到：{self.last_checkin}")

    def _update_next_label(self):
        svc = _get_service_config()
        t = svc.get("schedule_time", "09:00")
        try:
            h, m = map(int, t.split(":"))
            now = datetime.now()
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            self._lbl_next.configure(text=f"下次签到：{target.strftime('%Y-%m-%d %H:%M')}")
        except (ValueError, AttributeError):
            self._lbl_next.configure(text="下次签到：时间格式错误")

    # ══════════════════════════════════════════════════
    #  配置页回调
    # ══════════════════════════════════════════════════
    def _on_provider_change(self, choice):
        for v in DEFAULT_PROVIDERS.values():
            if v["name"] == choice:
                if v["base_url"]:
                    self._base_url_var.set(v["base_url"])
                    self._model_var.set(v["default_model"])
                break

    def _on_auth_toggle(self):
        if self._auth_var.get() == "https":
            self._token_frame.pack(fill="x", pady=(0, 0))
        else:
            self._token_frame.pack_forget()

    def _browse_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(initialdir=self._local_dir_var.get())
        if d:
            self._local_dir_var.set(d)

    def _on_ai_hist_select(self, name):
        history = load_config_history()
        for p in history.get("ai_profiles", []):
            if p["name"] == name:
                self._provider_var.set(p.get("provider", ""))
                self._base_url_var.set(p.get("base_url", ""))
                self._model_var.set(p.get("model", ""))
                self._apikey_var.set(p.get("api_key", ""))
                break

    def _on_gh_hist_select(self, name):
        history = load_config_history()
        for p in history.get("github_profiles", []):
            if p["name"] == name:
                self._repo_url_var.set(p.get("repo_url", ""))
                self._auth_var.set(p.get("auth_type", "ssh"))
                self._token_var.set(p.get("token", ""))
                self._local_dir_var.set(p.get("local_dir", ""))
                self._on_auth_toggle()
                break

    def _test_ai(self):
        self._ai_test_lbl.configure(text="⏳ 测试中…", text_color=GH_THEME["warning"])

        def worker():
            try:
                client = AIClient(self._base_url_var.get(),
                                  self._apikey_var.get(),
                                  self._model_var.get())
                ok, msg = client.test_connection()
                if ok:
                    self.after(0, lambda: self._ai_test_lbl.configure(
                        text=f"✅ {msg[:40]}", text_color=GH_THEME["success"]))
                else:
                    self.after(0, lambda: self._ai_test_lbl.configure(
                        text=f"❌ {msg[:50]}", text_color=GH_THEME["danger"]))
            except Exception as e:
                self.after(0, lambda: self._ai_test_lbl.configure(
                    text=f"❌ {e}", text_color=GH_THEME["danger"]))

        threading.Thread(target=worker, daemon=True).start()

    def _test_repo(self):
        self._repo_test_lbl.configure(text="⏳ 测试中…", text_color=GH_THEME["warning"])

        def worker():
            try:
                gh_cfg = {
                    "repo_url": self._repo_url_var.get().strip(),
                    "auth_type": self._auth_var.get(),
                    "local_dir": self._local_dir_var.get().strip(),
                }
                if gh_cfg["auth_type"] == "https":
                    token = self._token_var.get().strip()
                    gh_cfg["token"] = token
                    url = gh_cfg["repo_url"]
                    if url.startswith("https://github.com/"):
                        gh_cfg["repo_url_with_token"] = url.replace(
                            "https://github.com/", f"https://{token}@github.com/")

                gm = GitHubManager(gh_cfg)
                ok, msg = gm.test_connection()
                if ok:
                    self.after(0, lambda: self._repo_test_lbl.configure(
                        text=f"✅ {msg}", text_color=GH_THEME["success"]))
                else:
                    self.after(0, lambda: self._repo_test_lbl.configure(
                        text=f"❌ {msg[:60]}", text_color=GH_THEME["danger"]))
            except Exception as e:
                self.after(0, lambda: self._repo_test_lbl.configure(
                    text=f"❌ {e}", text_color=GH_THEME["danger"]))

        threading.Thread(target=worker, daemon=True).start()

    def _save_all_config(self):
        provider = self._provider_var.get()
        base_url = self._base_url_var.get().strip()
        model = self._model_var.get().strip()
        api_key = self._apikey_var.get().strip()
        repo_url = self._repo_url_var.get().strip()
        auth_type = self._auth_var.get()
        local_dir = self._local_dir_var.get().strip()

        if not base_url or not model or not api_key:
            from tkinter import messagebox
            messagebox.showerror("错误", "AI 配置不完整")
            return
        if not repo_url:
            from tkinter import messagebox
            messagebox.showerror("错误", "请填写 GitHub 仓库地址")
            return

        config = load_config() or {}
        config["ai"] = {"provider": provider, "base_url": base_url,
                        "model": model, "api_key": api_key}
        gh = {"repo_url": repo_url, "auth_type": auth_type,
              "local_dir": os.path.abspath(local_dir)}
        if auth_type == "https":
            token = self._token_var.get().strip()
            gh["token"] = token
            if repo_url.startswith("https://github.com/"):
                gh["repo_url_with_token"] = repo_url.replace(
                    "https://github.com/", f"https://{token}@github.com/")
        config["github"] = gh
        save_config(config)

        # 保存到历史
        ai_profile_name = f"{provider} / {model}"
        add_ai_profile({"name": ai_profile_name, "provider": provider,
                        "base_url": base_url, "model": model, "api_key": api_key})
        gh_profile_name = repo_url.split("/")[-1].replace(".git", "") if "/" in repo_url else repo_url
        add_github_profile({"name": gh_profile_name, "repo_url": repo_url,
                            "auth_type": auth_type, "token": self._token_var.get().strip(),
                            "local_dir": os.path.abspath(local_dir)})

        # 刷新历史下拉
        self._refresh_history_combos()

        self._log("✅ 配置已保存")
        from tkinter import messagebox
        messagebox.showinfo("提示", "配置已保存！")

    def _refresh_history_combos(self):
        history = load_config_history()
        ai_names = [p["name"] for p in history.get("ai_profiles", [])]
        gh_names = [p["name"] for p in history.get("github_profiles", [])]
        if self._ai_hist_combo:
            self._ai_hist_combo.configure(values=ai_names if ai_names else ["（无历史记录）"])
        if self._gh_hist_combo:
            self._gh_hist_combo.configure(values=gh_names if gh_names else ["（无历史记录）"])

    # ══════════════════════════════════════════════════
    #  设置页回调
    # ══════════════════════════════════════════════════
    def _save_settings(self):
        time_str = self._time_var.get().strip()
        port_str = self._port_var.get().strip()
        try:
            h, m = map(int, time_str.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            from tkinter import messagebox
            messagebox.showerror("错误", "时间格式不正确 (HH:MM)")
            return
        try:
            port = int(port_str)
            if not (1024 <= port <= 65535):
                raise ValueError
        except ValueError:
            from tkinter import messagebox
            messagebox.showerror("错误", "端口号需要在 1024-65535 之间")
            return

        svc = _get_service_config()
        svc["schedule_time"] = time_str
        svc["port"] = port
        svc["minimize_to_tray"] = self._minimize_var.get()
        svc["auto_start"] = self._auto_start_var.get()
        svc["silent_start"] = self._silent_var.get()
        _save_service_config(svc)

        _set_auto_start(self._auto_start_var.get(), self._silent_var.get())

        schedule.clear()
        schedule.every().day.at(time_str).do(
            lambda: self.after(0, lambda: self._do_checkin())
        )
        self._update_next_label()
        self._log(f"✅ 设置已保存 (时间={time_str}, 端口={port})")
        from tkinter import messagebox
        messagebox.showinfo("提示", "设置已保存！\n端口变更需重启应用后生效。")

    # ══════════════════════════════════════════════════
    #  托盘 & 定时
    # ══════════════════════════════════════════════════
    def _setup_tray(self):
        def on_show(icon, item):
            self.after(0, self._show_window)

        def on_quit(icon, item):
            self.after(0, self._quit)

        self.tray_icon = pystray.Icon(
            APP_NAME, _create_tray_image(), "GitHub 每日签到",
            menu=pystray.Menu(
                pystray.MenuItem("显示窗口", on_show, default=True),
                pystray.MenuItem("立即签到", lambda i, item: self.after(0, self._do_checkin)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", on_quit),
            ),
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _hide_to_tray(self):
        self.withdraw()
        self._log("窗口已最小化到托盘")

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self):
        if self._minimize_var.get():
            self._hide_to_tray()
        else:
            self._quit()

    def _quit(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()

    def _setup_scheduler(self):
        svc = _get_service_config()
        t = svc.get("schedule_time", "09:00")
        schedule.every().day.at(t).do(
            lambda: self.after(0, lambda: self._do_checkin())
        )
        self._log(f"⏰ 定时签到已设置：每天 {t}")

        def loop():
            while True:
                schedule.run_pending()
                time.sleep(30)

        threading.Thread(target=loop, daemon=True).start()

    def _start_http(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        app_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>签到状态</title></head><body style="font-family:sans-serif;max-width:500px;margin:50px auto">
<h2>GitHub 每日签到</h2>
<p>上次: {app_ref.last_checkin or '尚未'}</p>
<p>结果: {app_ref.last_result or '-'}</p>
<p>状态: {'签到中' if app_ref.is_running else '空闲'}</p>
</body></html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())

            def log_message(self, *a):
                pass

        svc = _get_service_config()
        port = svc["port"]
        try:
            server = HTTPServer(("127.0.0.1", port), Handler)
            self._log(f"🌐 状态页: http://localhost:{port}")
            server.serve_forever()
        except OSError as e:
            self._log(f"⚠️ 状态页启动失败 (端口 {port}): {e}")

    # ──────────────────────────────────────────────────
    def run(self):
        threading.Thread(target=self._start_http, daemon=True).start()
        self.mainloop()


# ══════════════════════════════════════════════════════
def main():
    minimized = "--minimized" in sys.argv or "--silent" in sys.argv
    app = CheckinApp(start_minimized=minimized)
    app.run()


if __name__ == "__main__":
    main()
