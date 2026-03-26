"""GitHub 管理模块 - 仓库操作（clone/pull/commit/push）"""

import os
from datetime import datetime

import git


class GitHubManager:
    def __init__(self, github_config):
        self.config = github_config
        self.local_dir = github_config["local_dir"]
        self.repo = None

    def _get_clone_url(self):
        """获取用于 clone 的 URL"""
        if self.config["auth_type"] == "https" and "repo_url_with_token" in self.config:
            return self.config["repo_url_with_token"]
        return self.config["repo_url"]

    def ensure_repo(self):
        """确保本地仓库存在且是最新的"""
        if os.path.exists(os.path.join(self.local_dir, ".git")):
            print(f"打开已有仓库: {self.local_dir}")
            self.repo = git.Repo(self.local_dir)
            self._pull()
        else:
            self._clone()

    def _clone(self):
        """克隆远程仓库"""
        url = self._get_clone_url()
        print(f"克隆仓库到: {self.local_dir}")
        self.repo = git.Repo.clone_from(url, self.local_dir)
        print("克隆完成。")

    def _pull(self):
        """拉取最新代码"""
        try:
            origin = self.repo.remotes.origin
            origin.pull()
            print("已拉取最新代码。")
        except Exception as e:
            print(f"拉取失败（可能是空仓库或无远程分支）: {e}")

    def save_and_push(self, filename, content, commit_msg=None):
        """保存文件并推送到远程"""
        # 按年/月组织目录
        today = datetime.now()
        rel_dir = os.path.join(str(today.year), f"{today.month:02d}")
        full_dir = os.path.join(self.local_dir, rel_dir)
        os.makedirs(full_dir, exist_ok=True)

        # 写入文件
        file_path = os.path.join(full_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"文件已保存: {os.path.join(rel_dir, filename)}")

        # Git add + commit + push
        self.repo.index.add([os.path.join(rel_dir, filename)])
        if not commit_msg:
            commit_msg = f"daily: {today.strftime('%Y-%m-%d')} - {filename}"
        self.repo.index.commit(commit_msg)
        print(f"已提交: {commit_msg}")

        origin = self.repo.remotes.origin
        origin.push()
        print("已推送到远程仓库。")

        return file_path

    def save_local_only(self, filename, content):
        """仅保存到本地（dry-run 模式）"""
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)

        file_path = os.path.join(output_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[dry-run] 文件已保存到本地: {file_path}")
        return file_path
