"""静默托盘入口 - 默认只在系统托盘运行，按需弹出设置窗口"""

import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

import customtkinter as ctk
import pystray
import schedule
from pystray import Menu, MenuItem

from main import run_checkin
from service import (
    APP_NAME,
    APP_TITLE,
    SingleInstance,
    create_tray_image,
    get_logger,
    get_service_config,
    is_auto_start,
    notify,
    save_service_config,
    set_auto_start,
)
from settings_window import SettingsWindow

SCHEDULE_PRESETS = ["08:00", "09:00", "10:00", "12:00", "18:00", "20:00", "22:00"]


class TrayApp:
    def __init__(self):
        self.logger = get_logger()
        self.is_running = False
        self.last_result = None
        self.icon = None

        ctk.set_appearance_mode("system")
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

    # ── 托盘菜单 ──
    def _build_menu(self):
        def make_time_action(time_str):
            def action(_icon, _item):
                self._set_schedule_time(time_str)
            return action

        def make_time_checked(time_str):
            def checked(_item):
                return get_service_config().get("schedule_time") == time_str
            return checked

        time_items = [
            MenuItem(t, make_time_action(t), checked=make_time_checked(t), radio=True)
            for t in SCHEDULE_PRESETS
        ]

        return Menu(
            MenuItem(APP_TITLE, None, enabled=False),
            MenuItem(self._status_text, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("立即签到", self._on_checkin, enabled=self._can_checkin),
            MenuItem("预览（不推送）", self._on_preview, enabled=self._can_checkin),
            Menu.SEPARATOR,
            MenuItem("设置…", self._on_settings, default=True),
            MenuItem("签到时间", Menu(*time_items)),
            MenuItem("开机启动", self._toggle_autostart, checked=self._is_autostart_checked),
            Menu.SEPARATOR,
            MenuItem("退出", self._on_quit),
        )

    def _status_text(self, _item=None):
        if self.is_running:
            return "● 正在签到…"
        svc = get_service_config()
        t = svc.get("schedule_time", "09:00")
        try:
            h, m = map(int, t.split(":"))
            now = datetime.now()
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return f"下次签到：{target.strftime('%m-%d %H:%M')}"
        except (ValueError, AttributeError):
            return f"下次签到：{t}"

    def _can_checkin(self, _item=None):
        return not self.is_running

    def _is_autostart_checked(self, _item=None):
        return is_auto_start()

    # ── 菜单回调 ──
    def _on_settings(self, _icon=None, _item=None):
        self.root.after(0, lambda: SettingsWindow.open(self.root))

    def _on_checkin(self, _icon=None, _item=None):
        self._start_checkin(dry_run=False)

    def _on_preview(self, _icon=None, _item=None):
        self._start_checkin(dry_run=True)

    def _set_schedule_time(self, t):
        svc = get_service_config()
        svc["schedule_time"] = t
        save_service_config(svc)
        self._reschedule(t)
        self.logger.info(f"签到时间已更新为 {t}")
        if self.icon:
            self.icon.update_menu()

    def _toggle_autostart(self, _icon=None, _item=None):
        set_auto_start(not is_auto_start())
        if self.icon:
            self.icon.update_menu()

    def _on_quit(self, _icon=None, _item=None):
        self.logger.info("应用退出")
        if self.icon:
            self.icon.visible = False
            self.icon.stop()
        self.root.after(0, self.root.destroy)

    # ── 签到执行 ──
    def _start_checkin(self, dry_run):
        if self.is_running:
            notify(self.icon, APP_TITLE, "已有签到任务在运行")
            return

        def worker():
            self.is_running = True
            if self.icon:
                self.icon.update_menu()
            mode = "预览" if dry_run else "签到"
            self.logger.info(f"开始{mode}")
            old_stdout = sys.stdout
            from service import LoggerStream
            sys.stdout = LoggerStream()
            try:
                run_checkin(dry_run=dry_run)
                self.last_result = "成功"
                notify(self.icon, APP_TITLE, f"{mode}成功")
                self.logger.info(f"{mode}完成")
            except Exception as e:
                self.last_result = f"失败: {e}"
                self.logger.error(f"{mode}失败: {traceback.format_exc()}")
                notify(self.icon, f"{APP_TITLE} - 失败", f"{mode}失败：{e}")
            finally:
                sys.stdout = old_stdout
                self.is_running = False
                if self.icon:
                    self.icon.update_menu()

        threading.Thread(target=worker, daemon=True).start()

    # ── 调度 ──
    def _reschedule(self, t):
        schedule.clear()
        schedule.every().day.at(t).do(lambda: self._start_checkin(dry_run=False))

    def _scheduler_loop(self):
        while True:
            schedule.run_pending()
            time.sleep(30)

    # ── 首次启动引导 ──
    def _maybe_prompt_first_run(self):
        from config_manager import load_config
        cfg = load_config()
        has_ai = cfg and cfg.get("ai", {}).get("api_key")
        has_gh = cfg and cfg.get("github", {}).get("repo_url")
        if not (has_ai and has_gh):
            self.logger.info("未检测到完整配置，弹出设置窗口")
            notify(self.icon, APP_TITLE, "请在设置中添加 API 与仓库信息")
            self.root.after(800, lambda: SettingsWindow.open(self.root))

    # ── 启动 ──
    def run(self):
        self.logger.info("应用启动")

        svc = get_service_config()
        self._reschedule(svc.get("schedule_time", "09:00"))
        threading.Thread(target=self._scheduler_loop, daemon=True).start()

        self.icon = pystray.Icon(APP_NAME, create_tray_image(), APP_TITLE, self._build_menu())
        threading.Thread(target=self.icon.run, daemon=True).start()

        self.root.after(1500, self._maybe_prompt_first_run)
        self.root.mainloop()


def main():
    lock = SingleInstance()
    if not lock.acquire():
        get_logger().info("已有实例在运行，退出")
        sys.exit(0)
    try:
        TrayApp().run()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
