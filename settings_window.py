"""设置窗口 - 简洁单页：AI 配置 + GitHub 配置"""

import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ai_client import AIClient
from config_manager import (
    DEFAULT_PROVIDERS,
    add_ai_profile,
    add_github_profile,
    load_config,
    load_config_history,
    save_config,
)
from github_manager import GitHubManager
from service import BASE_DIR, get_logger

FONT = "Microsoft YaHei UI"

THEME = {
    "primary": "#1f6feb",
    "primary_hover": "#388bfd",
    "success": "#238636",
    "danger": "#da3633",
    "warning": "#d29922",
    "text_dim": "#8b949e",
}


class SettingsWindow(ctk.CTkToplevel):
    """按需弹出的设置窗口，关闭即销毁"""

    _instance = None

    @classmethod
    def open(cls, master):
        if cls._instance is not None and cls._instance.winfo_exists():
            cls._instance.deiconify()
            cls._instance.lift()
            cls._instance.focus_force()
            return cls._instance
        cls._instance = cls(master)
        return cls._instance

    def __init__(self, master):
        super().__init__(master)
        self.title("设置 - GitHub 每日签到")
        self.geometry("580x680")
        self.minsize(560, 640)
        self.resizable(True, True)

        self.after(200, lambda: self.iconbitmap(default="") if False else None)

        self._center_on_screen(580, 680)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        config = load_config() or {}
        ai_cfg = config.get("ai", {})
        gh_cfg = config.get("github", {})
        history = load_config_history()

        # ── 根容器 ──
        root = ctk.CTkScrollableFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=20, pady=(18, 12))

        ctk.CTkLabel(root, text="设置", font=(FONT, 22, "bold")).pack(anchor="w", pady=(0, 14))

        # ── AI 卡片 ──
        ai_card = self._card(root, "AI 模型")

        ai_names = [p["name"] for p in history.get("ai_profiles", [])] or ["（无历史记录）"]
        self._ai_hist = ctk.StringVar()
        self._field_combo(ai_card, "历史配置", self._ai_hist, ai_names, self._on_ai_hist_select)

        self._provider = ctk.StringVar(value=ai_cfg.get("provider", "SiliconFlow"))
        self._field_combo(
            ai_card, "服务商", self._provider,
            [v["name"] for v in DEFAULT_PROVIDERS.values()],
            self._on_provider_change,
        )

        self._base_url = ctk.StringVar(value=ai_cfg.get("base_url", ""))
        self._field_entry(ai_card, "API 地址", self._base_url)

        self._model = ctk.StringVar(value=ai_cfg.get("model", ""))
        self._field_entry(ai_card, "模型名称", self._model)

        self._api_key = ctk.StringVar(value=ai_cfg.get("api_key", ""))
        self._field_entry(ai_card, "API Key", self._api_key, show="*")

        self._ai_status = self._test_row(ai_card, "测试 AI 连接", self._test_ai)

        # ── GitHub 卡片 ──
        gh_card = self._card(root, "GitHub 仓库")

        gh_names = [p["name"] for p in history.get("github_profiles", [])] or ["（无历史记录）"]
        self._gh_hist = ctk.StringVar()
        self._field_combo(gh_card, "历史配置", self._gh_hist, gh_names, self._on_gh_hist_select)

        self._repo_url = ctk.StringVar(value=gh_cfg.get("repo_url", ""))
        self._field_entry(gh_card, "仓库地址", self._repo_url)

        self._auth = ctk.StringVar(value=gh_cfg.get("auth_type", "ssh"))
        auth_row = ctk.CTkFrame(gh_card, fg_color="transparent")
        auth_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(auth_row, text="认证方式", font=(FONT, 13), width=100, anchor="w").pack(side="left")
        ctk.CTkRadioButton(
            auth_row, text="SSH", variable=self._auth, value="ssh",
            font=(FONT, 13), command=self._on_auth_toggle,
        ).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(
            auth_row, text="HTTPS + Token", variable=self._auth, value="https",
            font=(FONT, 13), command=self._on_auth_toggle,
        ).pack(side="left")

        self._token = ctk.StringVar(value=gh_cfg.get("token", ""))
        self._token_row = self._make_row(gh_card, "Token", self._token, show="*", auto_pack=False)
        if self._auth.get() == "https":
            self._token_row.pack(fill="x", padx=16, pady=4)

        self._local_dir = ctk.StringVar(value=gh_cfg.get("local_dir", os.path.join(BASE_DIR, "repo")))
        dir_row = ctk.CTkFrame(gh_card, fg_color="transparent")
        dir_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(dir_row, text="本地目录", font=(FONT, 13), width=100, anchor="w").pack(side="left")
        ctk.CTkEntry(dir_row, textvariable=self._local_dir, font=(FONT, 13), height=32).pack(
            side="left", fill="x", expand=True
        )
        ctk.CTkButton(
            dir_row, text="浏览", width=60, height=32, font=(FONT, 12),
            fg_color="transparent", border_width=1, text_color=("gray20", "gray80"),
            command=self._browse_dir,
        ).pack(side="left", padx=(6, 0))

        self._gh_status = self._test_row(gh_card, "测试仓库连接", self._test_repo)

        # ── 底部按钮 ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(
            btn_row, text="取消", width=88, height=36, font=(FONT, 13),
            fg_color="transparent", border_width=1, text_color=("gray20", "gray80"),
            command=self._on_close,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_row, text="保存", width=110, height=36, font=(FONT, 13, "bold"),
            fg_color=THEME["primary"], hover_color=THEME["primary_hover"],
            command=self._save,
        ).pack(side="right")

    # ── UI helpers ──
    def _center_on_screen(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _card(self, parent, title):
        frame = ctk.CTkFrame(parent, corner_radius=10, border_width=1)
        frame.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(frame, text=title, font=(FONT, 15, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkFrame(frame, height=1, fg_color=("gray80", "gray30")).pack(fill="x", padx=0)
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", pady=(8, 12))
        return inner

    def _make_row(self, parent, label, var, show=None, auto_pack=True):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        if auto_pack:
            row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text=label, font=(FONT, 13), width=100, anchor="w").pack(side="left")
        kw = dict(textvariable=var, font=(FONT, 13), height=32)
        if show:
            kw["show"] = show
        ctk.CTkEntry(row, **kw).pack(side="left", fill="x", expand=True)
        return row

    def _field_entry(self, parent, label, var, show=None):
        return self._make_row(parent, label, var, show=show)

    def _field_combo(self, parent, label, var, values, callback):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text=label, font=(FONT, 13), width=100, anchor="w").pack(side="left")
        ctk.CTkComboBox(
            row, variable=var, values=values, font=(FONT, 13), height=32,
            state="readonly", command=callback,
        ).pack(side="left", fill="x", expand=True)

    def _test_row(self, parent, btn_text, callback):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(6, 4))
        ctk.CTkFrame(row, width=100, fg_color="transparent").pack(side="left")
        ctk.CTkButton(
            row, text=btn_text, width=130, height=32, font=(FONT, 13),
            fg_color="transparent", border_width=1, text_color=("gray20", "gray80"),
            command=callback,
        ).pack(side="left")
        lbl = ctk.CTkLabel(row, text="", font=(FONT, 12), text_color=THEME["text_dim"])
        lbl.pack(side="left", padx=(10, 0))
        return lbl

    # ── 回调 ──
    def _on_provider_change(self, choice):
        for v in DEFAULT_PROVIDERS.values():
            if v["name"] == choice:
                if v["base_url"]:
                    self._base_url.set(v["base_url"])
                    self._model.set(v["default_model"])
                break

    def _on_auth_toggle(self):
        if self._auth.get() == "https":
            self._token_row.pack(fill="x", padx=16, pady=4)
        else:
            self._token_row.pack_forget()

    def _on_ai_hist_select(self, name):
        for p in load_config_history().get("ai_profiles", []):
            if p["name"] == name:
                self._provider.set(p.get("provider", ""))
                self._base_url.set(p.get("base_url", ""))
                self._model.set(p.get("model", ""))
                self._api_key.set(p.get("api_key", ""))
                return

    def _on_gh_hist_select(self, name):
        for p in load_config_history().get("github_profiles", []):
            if p["name"] == name:
                self._repo_url.set(p.get("repo_url", ""))
                self._auth.set(p.get("auth_type", "ssh"))
                self._token.set(p.get("token", ""))
                self._local_dir.set(p.get("local_dir", ""))
                self._on_auth_toggle()
                return

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self._local_dir.get())
        if d:
            self._local_dir.set(d)

    def _test_ai(self):
        self._ai_status.configure(text="测试中…", text_color=THEME["warning"])

        def worker():
            try:
                client = AIClient(self._base_url.get(), self._api_key.get(), self._model.get())
                ok, msg = client.test_connection()
                color = THEME["success"] if ok else THEME["danger"]
                prefix = "✓ " if ok else "✗ "
                self.after(0, lambda: self._ai_status.configure(
                    text=f"{prefix}{str(msg)[:40]}", text_color=color,
                ))
            except Exception as e:
                self.after(0, lambda: self._ai_status.configure(
                    text=f"✗ {e}", text_color=THEME["danger"],
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _test_repo(self):
        self._gh_status.configure(text="测试中…", text_color=THEME["warning"])

        def worker():
            try:
                cfg = self._build_gh_cfg()
                gm = GitHubManager(cfg)
                ok, msg = gm.test_connection()
                color = THEME["success"] if ok else THEME["danger"]
                prefix = "✓ " if ok else "✗ "
                self.after(0, lambda: self._gh_status.configure(
                    text=f"{prefix}{str(msg)[:60]}", text_color=color,
                ))
            except Exception as e:
                self.after(0, lambda: self._gh_status.configure(
                    text=f"✗ {e}", text_color=THEME["danger"],
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _build_gh_cfg(self):
        repo_url = self._repo_url.get().strip()
        cfg = {
            "repo_url": repo_url,
            "auth_type": self._auth.get(),
            "local_dir": os.path.abspath(self._local_dir.get().strip()),
        }
        if cfg["auth_type"] == "https":
            token = self._token.get().strip()
            cfg["token"] = token
            if repo_url.startswith("https://github.com/") and token:
                cfg["repo_url_with_token"] = repo_url.replace(
                    "https://github.com/", f"https://{token}@github.com/"
                )
        return cfg

    def _save(self):
        base_url = self._base_url.get().strip()
        model = self._model.get().strip()
        api_key = self._api_key.get().strip()
        repo_url = self._repo_url.get().strip()

        if not base_url or not model or not api_key:
            messagebox.showerror("错误", "AI 配置不完整", parent=self)
            return
        if not repo_url:
            messagebox.showerror("错误", "请填写 GitHub 仓库地址", parent=self)
            return

        config = load_config() or {}
        config["ai"] = {
            "provider": self._provider.get(),
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
        }
        config["github"] = self._build_gh_cfg()
        save_config(config)

        add_ai_profile({
            "name": f"{self._provider.get()} / {model}",
            "provider": self._provider.get(),
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
        })
        gh_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "") or repo_url
        add_github_profile({
            "name": gh_name,
            "repo_url": repo_url,
            "auth_type": self._auth.get(),
            "token": self._token.get().strip(),
            "local_dir": os.path.abspath(self._local_dir.get().strip()),
        })

        get_logger().info("配置已保存")
        self._on_close()

    def _on_close(self):
        SettingsWindow._instance = None
        self.destroy()
