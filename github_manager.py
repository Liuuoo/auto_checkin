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
            curr_branch = self.repo.active_branch.name
            print(f"正在从远程拉取分支: {curr_branch}...")
            origin.pull()
            print("已成功拉取最新代码。")
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
        print(f"正在推送到远程分支: {self.repo.active_branch.name}...")
        push_info = origin.push()
        for info in push_info:
            print(f"推送完成: {info.summary}")
        print("已成功推送到远程仓库。")

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

    def test_connection(self):
        """测试仓库连接：检测 Git 是否可用、远程仓库是否可达。
        返回 (bool, str) ——成功/失败和描述信息。
        """
        import subprocess

        # 1. 检测 git 是否可用
        try:
            result = subprocess.run(
                ["git", "--version"], capture_output=True, text=True, timeout=10
            )
            git_version = result.stdout.strip()
            print(f"Git 版本: {git_version}")
        except FileNotFoundError:
            return False, "未检测到 Git，请先安装 Git"
        except Exception as e:
            return False, f"Git 检测失败: {e}"

        # 2. 检测远程仓库是否可达
        url = self._get_clone_url()
        try:
            print(f"正在测试远程仓库连接: {self.config['repo_url']}...")
            result = subprocess.run(
                ["git", "ls-remote", "--exit-code", url],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return True, "仓库连接成功！远程仓库可达。"
            else:
                return False, f"仓库不可达: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return False, "连接超时（30 秒），请检查网络或 SSH 配置"
        except Exception as e:
            return False, f"连接测试失败: {e}"
