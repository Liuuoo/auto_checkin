"""GitHub 每日签到 - GUI 桌面应用"""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime, timedelta
import winreg

import schedule
import pystray
from PIL import Image, ImageDraw

from config_manager import load_config, save_config
from content_generator import get_topic_names
from main import run_checkin

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "GitHubDailyCheckin"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


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
    draw.ellipse([4, 4, 60, 60], fill=(34, 139, 34))
    draw.line([(18, 34), (28, 46), (46, 20)], fill="white", width=5)
    return img


class CheckinApp:
    def __init__(self, start_minimized=False):
        self.root = tk.Tk()
        self.root.title("GitHub 每日签到工具")
        self.root.geometry("520x720")
        self.root.resizable(False, False)
        self.root.configure(bg="#f0f0f0")

        self.is_running = False
        self.last_checkin = None
        self.last_result = None
        self.tray_icon = None
        self.start_minimized = start_minimized

        self._build_ui()
        self._setup_scheduler()
        self._setup_tray()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if start_minimized:
            self.root.after(100, self._hide_to_tray)

    def _build_ui(self):
        root = self.root
        pad = {"padx": 12, "pady": 4}

        # ===== 标题 =====
        title = tk.Label(root, text="GitHub 每日签到工具", font=("Microsoft YaHei UI", 16, "bold"),
                         bg="#f0f0f0", fg="#333")
        title.pack(pady=(16, 8))

        # ===== 状态面板 =====
        status_frame = tk.LabelFrame(root, text="  运行状态  ", font=("Microsoft YaHei UI", 10),
                                     bg="#fff", fg="#333", bd=1, relief="groove")
        status_frame.pack(fill="x", **pad)

        self.status_label = tk.Label(status_frame, text="● 服务运行中", font=("Microsoft YaHei UI", 11),
                                     bg="#fff", fg="#228B22", anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=(8, 2))

        self.last_checkin_label = tk.Label(status_frame, text="上次签到：尚未签到",
                                           font=("Microsoft YaHei UI", 9), bg="#fff", fg="#666", anchor="w")
        self.last_checkin_label.pack(fill="x", padx=12)

        self.last_result_label = tk.Label(status_frame, text="签到结果：-",
                                          font=("Microsoft YaHei UI", 9), bg="#fff", fg="#666", anchor="w")
        self.last_result_label.pack(fill="x", padx=12)

        self.next_checkin_label = tk.Label(status_frame, text="下次签到：-",
                                           font=("Microsoft YaHei UI", 9), bg="#fff", fg="#666", anchor="w")
        self.next_checkin_label.pack(fill="x", padx=12, pady=(0, 8))

        # ===== 签到选项 =====
        option_frame = tk.LabelFrame(root, text="  签到选项  ", font=("Microsoft YaHei UI", 10),
                                      bg="#fff", fg="#333", bd=1, relief="groove")
        option_frame.pack(fill="x", **pad)

        row_topic = tk.Frame(option_frame, bg="#fff")
        row_topic.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(row_topic, text="主题选择：", font=("Microsoft YaHei UI", 9), bg="#fff").pack(side="left")
        topic_choices = ["随机"] + get_topic_names()
        self.topic_var = tk.StringVar(value="随机")
        self.topic_combo = ttk.Combobox(row_topic, textvariable=self.topic_var, values=topic_choices,
                                         state="readonly", width=18, font=("Microsoft YaHei UI", 9))
        self.topic_combo.pack(side="left")

        row_count = tk.Frame(option_frame, bg="#fff")
        row_count.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(row_count, text="文章数量：", font=("Microsoft YaHei UI", 9), bg="#fff").pack(side="left")
        self.count_var = tk.StringVar(value="1")
        self.count_spin = tk.Spinbox(row_count, from_=1, to=10, textvariable=self.count_var,
                                      width=5, font=("Microsoft YaHei UI", 9))
        self.count_spin.pack(side="left")

        # ===== 操作按钮 =====
        btn_frame = tk.Frame(root, bg="#f0f0f0")
        btn_frame.pack(fill="x", **pad)

        self.checkin_btn = tk.Button(btn_frame, text="立即签到", font=("Microsoft YaHei UI", 10),
                                     bg="#228B22", fg="white", relief="flat", cursor="hand2",
                                     width=14, height=1, command=self._do_checkin)
        self.checkin_btn.pack(side="left", padx=(0, 8))

        self.preview_btn = tk.Button(btn_frame, text="预览 (不推送)", font=("Microsoft YaHei UI", 10),
                                     bg="#4a90d9", fg="white", relief="flat", cursor="hand2",
                                     width=14, height=1, command=self._do_preview)
        self.preview_btn.pack(side="left")

        # ===== 设置区 =====
        settings_frame = tk.LabelFrame(root, text="  设置  ", font=("Microsoft YaHei UI", 10),
                                        bg="#fff", fg="#333", bd=1, relief="groove")
        settings_frame.pack(fill="x", **pad)

        svc = get_service_config()

        row1 = tk.Frame(settings_frame, bg="#fff")
        row1.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(row1, text="每日签到时间：", font=("Microsoft YaHei UI", 9), bg="#fff").pack(side="left")
        self.time_var = tk.StringVar(value=svc.get("schedule_time", "09:00"))
        self.time_entry = tk.Entry(row1, textvariable=self.time_var, width=8,
                                    font=("Microsoft YaHei UI", 9))
        self.time_entry.pack(side="left")
        tk.Label(row1, text="  (格式 HH:MM)", font=("Microsoft YaHei UI", 8), bg="#fff", fg="#999").pack(side="left")

        row2 = tk.Frame(settings_frame, bg="#fff")
        row2.pack(fill="x", padx=12, pady=4)
        tk.Label(row2, text="状态页端口：    ", font=("Microsoft YaHei UI", 9), bg="#fff").pack(side="left")
        self.port_var = tk.StringVar(value=str(svc.get("port", 5000)))
        self.port_entry = tk.Entry(row2, textvariable=self.port_var, width=8,
                                    font=("Microsoft YaHei UI", 9))
        self.port_entry.pack(side="left")

        self.autostart_var = tk.BooleanVar(value=is_auto_start_enabled())
        cb1 = tk.Checkbutton(settings_frame, text="开机自动启动", variable=self.autostart_var,
                              font=("Microsoft YaHei UI", 9), bg="#fff", activebackground="#fff")
        cb1.pack(anchor="w", padx=12, pady=2)

        self.minimize_var = tk.BooleanVar(value=svc.get("minimize_to_tray", True))
        cb2 = tk.Checkbutton(settings_frame, text="关闭窗口时最小化到托盘", variable=self.minimize_var,
                              font=("Microsoft YaHei UI", 9), bg="#fff", activebackground="#fff")
        cb2.pack(anchor="w", padx=12, pady=(2, 4))

        save_btn = tk.Button(settings_frame, text="保存设置", font=("Microsoft YaHei UI", 9),
                              bg="#555", fg="white", relief="flat", cursor="hand2",
                              command=self._save_settings)
        save_btn.pack(anchor="w", padx=12, pady=(4, 10))

        # ===== 日志区 =====
        log_frame = tk.LabelFrame(root, text="  运行日志  ", font=("Microsoft YaHei UI", 10),
                                   bg="#fff", fg="#333", bd=1, relief="groove")
        log_frame.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 9),
                                                   bg="#1e1e1e", fg="#d4d4d4", insertbackground="#fff",
                                                   state="disabled", wrap="word", bd=0)
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        self._log("应用已启动")
        self._update_next_checkin()

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_status(self):
        if self.is_running:
            self.status_label.configure(text="● 签到中...", fg="#d4a017")
        else:
            self.status_label.configure(text="● 服务运行中", fg="#228B22")

        if self.last_checkin:
            self.last_checkin_label.configure(text=f"上次签到：{self.last_checkin}")
        if self.last_result:
            color = "#228B22" if self.last_result == "成功" else "#cc3333"
            self.last_result_label.configure(text=f"签到结果：{self.last_result}", fg=color)

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

        # 验证时间格式
        try:
            h, m = map(int, time_str.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            messagebox.showerror("错误", "时间格式不正确，请输入 HH:MM 格式（如 09:00）")
            return

        # 验证端口
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

        # 处理开机自启
        set_auto_start(self.autostart_var.get())

        # 重新设置定时任务
        schedule.clear()
        schedule.every().day.at(time_str).do(
            lambda: self.root.after(0, lambda: self._do_checkin())
        )

        self._update_next_checkin()
        self._log(f"设置已保存 (时间={time_str}, 端口={port})")
        messagebox.showinfo("提示", "设置已保存！\n端口变更需重启应用后生效。")

    # ===== 系统托盘 =====
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

    # ===== 定时任务 =====
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

    # ===== HTTP 状态页 =====
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
        # 启动 HTTP 状态页
        threading.Thread(target=self._start_http, daemon=True).start()
        self.root.mainloop()


def main():
    minimized = "--minimized" in sys.argv
    app = CheckinApp(start_minimized=minimized)
    app.run()


if __name__ == "__main__":
    main()
