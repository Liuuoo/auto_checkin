"""GitHub 每日签到 - GUI 桌面应用（美化版）"""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime, timedelta
import winreg

import schedule
import pystray
from PIL import Image, ImageDraw

from config_manager import DEFAULT_PROVIDERS, load_config, save_config
from content_generator import get_topic_names
from ai_client import AIClient
from main import run_checkin

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "GitHubDailyCheckin"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ===== 配色方案 =====
COLORS = {
    "bg": "#f0f2f5",
    "card": "#ffffff",
    "primary": "#2b5797",
    "primary_hover": "#1e3f6f",
    "success": "#228B22",
    "success_hover": "#1a6b1a",
    "warning": "#d4a017",
    "danger": "#cc3333",
    "text": "#1a1a2e",
    "text_secondary": "#6b7280",
    "border": "#e0e0e0",
    "log_bg": "#1e1e2e",
    "log_fg": "#cdd6f4",
}


def get_service_config():
    config = load_config()
    defaults = {"port": 5000, "auto_start": False, "schedule_time": "09:00", "minimize_to_tray": True}
    if not config:
        return defaults
    svc = config.get("service", {})
    for k, v in defaults.items():
        svc.setdefault(k, v)
    return svc


def save_service_config(service_cfg):
    config = load_config() or {}
    config["service"] = service_cfg
    save_config(config)


def is_auto_start_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False


def set_auto_start(enable):
    if enable:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable
        script = os.path.join(SCRIPT_DIR, "gui_app.py")
        cmd = f'"{pythonw}" "{script}" --minimized'
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


def create_tray_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=COLORS["primary"])
    draw.line([(18, 34), (28, 46), (46, 20)], fill="white", width=5)
    return img


def setup_styles():
    """配置 ttk 主题样式"""
    style = ttk.Style()
    style.theme_use("clam")

    # 通用
    style.configure(".", font=("Microsoft YaHei UI", 9), background=COLORS["bg"])
    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10, "bold"),
                    padding=[16, 8], background=COLORS["card"], foreground=COLORS["text_secondary"])
    style.map("TNotebook.Tab",
              background=[("selected", COLORS["primary"])],
              foreground=[("selected", "#ffffff")])

    # LabelFrame
    style.configure("Card.TLabelframe", background=COLORS["card"], borderwidth=1,
                    relief="solid", bordercolor=COLORS["border"])
    style.configure("Card.TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"),
                    background=COLORS["card"], foreground=COLORS["primary"])

    # Label
    style.configure("TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("Status.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
    style.configure("Secondary.TLabel", foreground=COLORS["text_secondary"])
    style.configure("Title.TLabel", font=("Microsoft YaHei UI", 9), background=COLORS["bg"],
                    foreground=COLORS["text_secondary"])

    # Entry
    style.configure("TEntry", fieldbackground="#fff", borderwidth=1)

    # Buttons
    style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                    background=COLORS["primary"], foreground="#ffffff", padding=[20, 8])
    style.map("Primary.TButton",
              background=[("active", COLORS["primary_hover"]), ("pressed", COLORS["primary_hover"])])

    style.configure("Success.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                    background=COLORS["success"], foreground="#ffffff", padding=[20, 8])
    style.map("Success.TButton",
              background=[("active", COLORS["success_hover"]), ("pressed", COLORS["success_hover"])])

    style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 9),
                    background="#6b7280", foreground="#ffffff", padding=[14, 6])
    style.map("Secondary.TButton",
              background=[("active", "#4b5563"), ("pressed", "#4b5563")])

    # Checkbutton
    style.configure("TCheckbutton", background=COLORS["card"], foreground=COLORS["text"],
                    font=("Microsoft YaHei UI", 9))

    # Frame
    style.configure("Card.TFrame", background=COLORS["card"])

    return style


class CheckinApp:
    def __init__(self, start_minimized=False):
        self.root = tk.Tk()
        self.root.title("GitHub 每日签到工具")
        self.root.geometry("580x750")
        self.root.minsize(520, 650)
        self.root.configure(bg=COLORS["bg"])

        self.is_running = False
        self.last_checkin = None
        self.last_result = None
        self.tray_icon = None
        self.start_minimized = start_minimized

        setup_styles()
        self._build_ui()
        self._setup_scheduler()
        self._setup_tray()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if start_minimized:
            self.root.after(100, self._hide_to_tray)

    # ================================================================
    #  UI 构建
    # ================================================================
    def _build_ui(self):
        root = self.root

        # 顶部标题栏
        header = tk.Frame(root, bg=COLORS["primary"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  GitHub 每日签到工具", font=("Microsoft YaHei UI", 14, "bold"),
                 bg=COLORS["primary"], fg="#ffffff", anchor="w").pack(fill="both", expand=True, padx=8)

        # Notebook 选项卡
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(12, 12))

        # 三个选项卡
        self.tab_checkin = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_config = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_settings = ttk.Frame(self.notebook, style="Card.TFrame")

        self.notebook.add(self.tab_checkin, text="  签到  ")
        self.notebook.add(self.tab_config, text="  配置  ")
        self.notebook.add(self.tab_settings, text="  设置  ")

        self._build_checkin_tab()
        self._build_config_tab()
        self._build_settings_tab()

    # ---------- 签到选项卡 ----------
    def _build_checkin_tab(self):
        tab = self.tab_checkin
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)  # 日志区扩展

        # 状态面板
        sf = ttk.LabelFrame(tab, text="运行状态", style="Card.TLabelframe")
        sf.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        sf.columnconfigure(1, weight=1)

        self.status_label = ttk.Label(sf, text="● 服务运行中", style="Status.TLabel",
                                       foreground=COLORS["success"])
        self.status_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))

        self.last_checkin_label = ttk.Label(sf, text="上次签到：尚未签到", style="Secondary.TLabel")
        self.last_checkin_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=1)

        self.last_result_label = ttk.Label(sf, text="签到结果：-", style="Secondary.TLabel")
        self.last_result_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=1)

        self.next_checkin_label = ttk.Label(sf, text="下次签到：-", style="Secondary.TLabel")
        self.next_checkin_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(1, 10))

        # 签到选项
        of = ttk.LabelFrame(tab, text="签到选项", style="Card.TLabelframe")
        of.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        of.columnconfigure(1, weight=1)

        ttk.Label(of, text="主题选择：").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        topic_choices = ["随机"] + get_topic_names()
        self.topic_var = tk.StringVar(value="随机")
        self.topic_combo = ttk.Combobox(of, textvariable=self.topic_var, values=topic_choices,
                                         state="readonly", width=22)
        self.topic_combo.grid(row=0, column=1, sticky="w", padx=4, pady=(10, 4))

        ttk.Label(of, text="文章数量：").grid(row=1, column=0, sticky="w", padx=12, pady=(4, 10))
        self.count_var = tk.StringVar(value="1")
        self.count_spin = ttk.Spinbox(of, from_=1, to=10, textvariable=self.count_var, width=6)
        self.count_spin.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 10))

        # 操作按钮
        bf = ttk.Frame(tab, style="Card.TFrame")
        bf.grid(row=2, column=0, sticky="ew", padx=12, pady=6)

        ttk.Button(bf, text="立即签到", style="Success.TButton",
                   command=self._do_checkin).pack(side="left", padx=(0, 8))
        ttk.Button(bf, text="预览 (不推送)", style="Primary.TButton",
                   command=self._do_preview).pack(side="left")

        # 日志区
        lf = ttk.LabelFrame(tab, text="运行日志", style="Card.TLabelframe")
        lf.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 12))
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(lf, font=("Consolas", 9),
                                                   bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                                   insertbackground="#fff", state="disabled",
                                                   wrap="word", bd=0, relief="flat")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        self._log("应用已启动")
        self._update_next_checkin()

    # ---------- 配置选项卡 ----------
    def _build_config_tab(self):
        tab = self.tab_config
        tab.columnconfigure(0, weight=1)

        config = load_config() or {}
        ai_cfg = config.get("ai", {})
        gh_cfg = config.get("github", {})

        # --- AI 配置 ---
        ai_frame = ttk.LabelFrame(tab, text="AI 模型配置", style="Card.TLabelframe")
        ai_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        ai_frame.columnconfigure(1, weight=1)

        ttk.Label(ai_frame, text="服务商：").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        providers = [v["name"] for v in DEFAULT_PROVIDERS.values()]
        self.provider_var = tk.StringVar(value=ai_cfg.get("provider", "SiliconFlow"))
        self.provider_combo = ttk.Combobox(ai_frame, textvariable=self.provider_var,
                                            values=providers, state="readonly", width=28)
        self.provider_combo.grid(row=0, column=1, sticky="ew", padx=(4, 12), pady=(10, 4))
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        ttk.Label(ai_frame, text="API 地址：").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.base_url_var = tk.StringVar(value=ai_cfg.get("base_url", ""))
        ttk.Entry(ai_frame, textvariable=self.base_url_var).grid(
            row=1, column=1, sticky="ew", padx=(4, 12), pady=4)

        ttk.Label(ai_frame, text="模型名称：").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.model_var = tk.StringVar(value=ai_cfg.get("model", ""))
        ttk.Entry(ai_frame, textvariable=self.model_var).grid(
            row=2, column=1, sticky="ew", padx=(4, 12), pady=4)

        ttk.Label(ai_frame, text="API Key：").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        self.apikey_var = tk.StringVar(value=ai_cfg.get("api_key", ""))
        ttk.Entry(ai_frame, textvariable=self.apikey_var, show="*").grid(
            row=3, column=1, sticky="ew", padx=(4, 12), pady=4)

        btn_row = ttk.Frame(ai_frame, style="Card.TFrame")
        btn_row.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 10))
        ttk.Button(btn_row, text="测试连接", style="Secondary.TButton",
                   command=self._test_connection).pack(side="left")
        self.test_result_label = ttk.Label(btn_row, text="", style="Secondary.TLabel")
        self.test_result_label.pack(side="left", padx=10)

        # --- GitHub 配置 ---
        gh_frame = ttk.LabelFrame(tab, text="GitHub 配置", style="Card.TLabelframe")
        gh_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        gh_frame.columnconfigure(1, weight=1)

        ttk.Label(gh_frame, text="仓库地址：").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.repo_url_var = tk.StringVar(value=gh_cfg.get("repo_url", ""))
        ttk.Entry(gh_frame, textvariable=self.repo_url_var).grid(
            row=0, column=1, sticky="ew", padx=(4, 12), pady=(10, 4))

        ttk.Label(gh_frame, text="认证方式：").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.auth_var = tk.StringVar(value=gh_cfg.get("auth_type", "ssh"))
        auth_frame = ttk.Frame(gh_frame, style="Card.TFrame")
        auth_frame.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(auth_frame, text="SSH", variable=self.auth_var, value="ssh",
                         command=self._on_auth_change).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(auth_frame, text="HTTPS + Token", variable=self.auth_var, value="https",
                         command=self._on_auth_change).pack(side="left")

        self.token_label = ttk.Label(gh_frame, text="Token：")
        self.token_var = tk.StringVar(value=gh_cfg.get("token", ""))
        self.token_entry = ttk.Entry(gh_frame, textvariable=self.token_var, show="*")
        if self.auth_var.get() == "https":
            self.token_label.grid(row=2, column=0, sticky="w", padx=12, pady=4)
            self.token_entry.grid(row=2, column=1, sticky="ew", padx=(4, 12), pady=4)

        ttk.Label(gh_frame, text="本地目录：").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        dir_frame = ttk.Frame(gh_frame, style="Card.TFrame")
        dir_frame.grid(row=3, column=1, sticky="ew", padx=(4, 12), pady=4)
        dir_frame.columnconfigure(0, weight=1)
        self.local_dir_var = tk.StringVar(value=gh_cfg.get("local_dir", os.path.join(SCRIPT_DIR, "repo")))
        ttk.Entry(dir_frame, textvariable=self.local_dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_frame, text="浏览", style="Secondary.TButton",
                   command=self._browse_dir).grid(row=0, column=1, padx=(4, 0))

        # 保存按钮
        ttk.Button(tab, text="保存配置", style="Primary.TButton",
                   command=self._save_config).grid(row=2, column=0, sticky="w", padx=12, pady=(10, 12))

    # ---------- 设置选项卡 ----------
    def _build_settings_tab(self):
        tab = self.tab_settings
        tab.columnconfigure(0, weight=1)

        svc = get_service_config()

        sf = ttk.LabelFrame(tab, text="服务设置", style="Card.TLabelframe")
        sf.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        sf.columnconfigure(1, weight=1)

        ttk.Label(sf, text="每日签到时间：").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        time_row = ttk.Frame(sf, style="Card.TFrame")
        time_row.grid(row=0, column=1, sticky="w", padx=4, pady=(10, 4))
        self.time_var = tk.StringVar(value=svc.get("schedule_time", "09:00"))
        ttk.Entry(time_row, textvariable=self.time_var, width=8).pack(side="left")
        ttk.Label(time_row, text="  (格式 HH:MM)", style="Secondary.TLabel").pack(side="left")

        ttk.Label(sf, text="状态页端口：").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.port_var = tk.StringVar(value=str(svc.get("port", 5000)))
        ttk.Entry(sf, textvariable=self.port_var, width=8).grid(
            row=1, column=1, sticky="w", padx=4, pady=4)

        self.autostart_var = tk.BooleanVar(value=is_auto_start_enabled())
        ttk.Checkbutton(sf, text="开机自动启动", variable=self.autostart_var).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=12, pady=4)

        self.minimize_var = tk.BooleanVar(value=svc.get("minimize_to_tray", True))
        ttk.Checkbutton(sf, text="关闭窗口时最小化到托盘", variable=self.minimize_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 10))

        ttk.Button(tab, text="保存设置", style="Primary.TButton",
                   command=self._save_settings).grid(row=1, column=0, sticky="w", padx=12, pady=(10, 12))

    # ================================================================
    #  配置页回调
    # ================================================================
    def _on_provider_change(self, event=None):
        name = self.provider_var.get()
        for v in DEFAULT_PROVIDERS.values():
            if v["name"] == name:
                if v["base_url"]:
                    self.base_url_var.set(v["base_url"])
                    self.model_var.set(v["default_model"])
                break

    def _on_auth_change(self):
        if self.auth_var.get() == "https":
            self.token_label.grid(row=2, column=0, sticky="w", padx=12, pady=4)
            self.token_entry.grid(row=2, column=1, sticky="ew", padx=(4, 12), pady=4)
        else:
            self.token_label.grid_forget()
            self.token_entry.grid_forget()

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.local_dir_var.get())
        if d:
            self.local_dir_var.set(d)

    def _test_connection(self):
        self.test_result_label.configure(text="测试中...", foreground=COLORS["warning"])

        def worker():
            try:
                client = AIClient(self.base_url_var.get(), self.apikey_var.get(), self.model_var.get())
                ok, msg = client.test_connection()
                if ok:
                    self.root.after(0, lambda: self.test_result_label.configure(
                        text=f"连接成功: {msg[:30]}", foreground=COLORS["success"]))
                else:
                    self.root.after(0, lambda: self.test_result_label.configure(
                        text=f"失败: {msg[:40]}", foreground=COLORS["danger"]))
            except Exception as e:
                self.root.after(0, lambda: self.test_result_label.configure(
                    text=f"错误: {e}", foreground=COLORS["danger"]))

        threading.Thread(target=worker, daemon=True).start()

    def _save_config(self):
        provider = self.provider_var.get()
        base_url = self.base_url_var.get().strip()
        model = self.model_var.get().strip()
        api_key = self.apikey_var.get().strip()
        repo_url = self.repo_url_var.get().strip()
        auth_type = self.auth_var.get()
        local_dir = self.local_dir_var.get().strip()

        if not base_url or not model or not api_key:
            messagebox.showerror("错误", "AI 配置不完整，请填写所有字段")
            return
        if not repo_url:
            messagebox.showerror("错误", "请填写 GitHub 仓库地址")
            return

        config = load_config() or {}
        config["ai"] = {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
        }
        gh = {
            "repo_url": repo_url,
            "auth_type": auth_type,
            "local_dir": os.path.abspath(local_dir),
        }
        if auth_type == "https":
            token = self.token_var.get().strip()
            gh["token"] = token
            if repo_url.startswith("https://github.com/"):
                gh["repo_url_with_token"] = repo_url.replace(
                    "https://github.com/", f"https://{token}@github.com/")
        config["github"] = gh
        save_config(config)
        self._log("配置已保存")
        messagebox.showinfo("提示", "配置已保存！")

    # ================================================================
    #  签到逻辑
    # ================================================================
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_status(self):
        if self.is_running:
            self.status_label.configure(text="● 签到中...", foreground=COLORS["warning"])
        else:
            self.status_label.configure(text="● 服务运行中", foreground=COLORS["success"])
        if self.last_checkin:
            self.last_checkin_label.configure(text=f"上次签到：{self.last_checkin}")
        if self.last_result:
            color = COLORS["success"] if self.last_result == "成功" else COLORS["danger"]
            self.last_result_label.configure(text=f"签到结果：{self.last_result}", foreground=color)

    def _update_next_checkin(self):
        svc = get_service_config()
        t = svc.get("schedule_time", "09:00")
        now = datetime.now()
        try:
            h, m = map(int, t.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            self.next_checkin_label.configure(text=f"下次签到：{target.strftime('%Y-%m-%d %H:%M')}")
        except (ValueError, AttributeError):
            self.next_checkin_label.configure(text="下次签到：时间格式错误")

    def _do_checkin(self, dry_run=False):
        if self.is_running:
            self._log("签到正在进行中，请稍候...")
            return

        topic = self.topic_var.get()
        topic_name = None if topic == "随机" else topic
        try:
            count = int(self.count_var.get())
            count = max(1, min(10, count))
        except ValueError:
            count = 1

        def worker():
            self.is_running = True
            self.root.after(0, self._update_status)
            mode = "预览" if dry_run else "签到"
            t_desc = topic_name or "随机主题"
            self.root.after(0, lambda: self._log(f"开始{mode} ({t_desc} x{count})..."))
            try:
                run_checkin(dry_run=dry_run, topic_name=topic_name, count=count)
                self.last_checkin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_result = "成功"
                self.root.after(0, lambda: self._log(f"{mode}完成！共 {count} 篇"))
            except Exception as e:
                self.last_checkin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_result = f"失败: {e}"
                self.root.after(0, lambda: self._log(f"{mode}失败: {e}"))
            finally:
                self.is_running = False
                self.root.after(0, self._update_status)
                self.root.after(0, self._update_next_checkin)

        threading.Thread(target=worker, daemon=True).start()

    def _do_preview(self):
        self._do_checkin(dry_run=True)

    def _save_settings(self):
        time_str = self.time_var.get().strip()
        port_str = self.port_var.get().strip()

        try:
            h, m = map(int, time_str.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            messagebox.showerror("错误", "时间格式不正确，请输入 HH:MM 格式（如 09:00）")
            return

        try:
            port = int(port_str)
            if not (1024 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "端口号需要在 1024-65535 之间")
            return

        svc = get_service_config()
        svc["schedule_time"] = time_str
        svc["port"] = port
        svc["minimize_to_tray"] = self.minimize_var.get()
        svc["auto_start"] = self.autostart_var.get()
        save_service_config(svc)

        set_auto_start(self.autostart_var.get())

        schedule.clear()
        schedule.every().day.at(time_str).do(
            lambda: self.root.after(0, lambda: self._do_checkin())
        )

        self._update_next_checkin()
        self._log(f"设置已保存 (时间={time_str}, 端口={port})")
        messagebox.showinfo("提示", "设置已保存！\n端口变更需重启应用后生效。")

    # ================================================================
    #  系统托盘
    # ================================================================
    def _setup_tray(self):
        def on_show(icon, item):
            self.root.after(0, self._show_window)

        def on_quit(icon, item):
            self.root.after(0, self._quit)

        self.tray_icon = pystray.Icon(
            APP_NAME,
            create_tray_icon_image(),
            "GitHub 每日签到",
            menu=pystray.Menu(
                pystray.MenuItem("显示窗口", on_show, default=True),
                pystray.MenuItem("立即签到", lambda icon, item: self.root.after(0, self._do_checkin)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", on_quit),
            ),
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _hide_to_tray(self):
        self.root.withdraw()
        self._log("窗口已最小化到托盘")

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self):
        if self.minimize_var.get():
            self._hide_to_tray()
        else:
            self._quit()

    def _quit(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    # ================================================================
    #  定时任务 & HTTP
    # ================================================================
    def _setup_scheduler(self):
        svc = get_service_config()
        t = svc.get("schedule_time", "09:00")
        schedule.every().day.at(t).do(
            lambda: self.root.after(0, lambda: self._do_checkin())
        )
        self._log(f"定时签到已设置：每天 {t}")

        def scheduler_loop():
            while True:
                schedule.run_pending()
                time.sleep(30)

        threading.Thread(target=scheduler_loop, daemon=True).start()

    def _start_http(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        app = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>GitHub 签到状态</title></head><body style="font-family:sans-serif;max-width:500px;margin:50px auto">
<h2>GitHub 每日签到</h2>
<p>上次签到：{app.last_checkin or '尚未签到'}</p>
<p>结果：{app.last_result or '-'}</p>
<p>状态：{'签到中' if app.is_running else '空闲'}</p>
</body></html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())

            def log_message(self, *a):
                pass

        svc = get_service_config()
        port = svc["port"]
        try:
            server = HTTPServer(("127.0.0.1", port), Handler)
            self._log(f"状态页已启动: http://localhost:{port}")
            server.serve_forever()
        except OSError as e:
            self._log(f"状态页启动失败 (端口 {port}): {e}")

    def run(self):
        threading.Thread(target=self._start_http, daemon=True).start()
        self.root.mainloop()


def main():
    minimized = "--minimized" in sys.argv
    app = CheckinApp(start_minimized=minimized)
    app.run()


if __name__ == "__main__":
    main()
