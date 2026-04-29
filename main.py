"""GitHub 每日签到 - 签到业务逻辑 + 托盘入口转发"""

from ai_client import AIClient
from config_manager import load_config
from content_generator import generate_content
from github_manager import GitHubManager


def run_checkin(dry_run=False, topic_name=None, count=1, on_article=None):
    """执行一次（或多次）签到。

    dry_run: 只生成不推送，仅落盘本地。
    topic_name: 指定主题名；None 随机。
    count: 生成篇数。
    on_article: 回调 (filename, content)，每生成一篇调用一次。
    """
    config = load_config()
    if not config:
        raise RuntimeError("未找到配置，请先在托盘菜单 → 设置 中完成配置")

    ai_cfg = config["ai"]
    client = AIClient(ai_cfg["base_url"], ai_cfg["api_key"], ai_cfg["model"])
    gm = GitHubManager(config["github"])

    if not dry_run:
        gm.ensure_repo()

    for i in range(count):
        if count > 1:
            print(f"===== 第 {i + 1}/{count} 篇 =====")
        print("正在生成今日内容...")
        filename, content, category, commit_msg = generate_content(client, topic_name=topic_name)
        print(f"生成完成: {filename} (分类: {category})")
        print(f"Commit 消息: {commit_msg}")
        print(f"内容长度: {len(content)} 字符")

        if on_article:
            on_article(filename, content)

        if dry_run:
            path = gm.save_local_only(filename, content)
            print(f"[dry-run] 预览文件: {path}")
        else:
            print("准备推送到 GitHub...")
            path = gm.save_and_push(filename, content, commit_msg)
            print(f"签到完成！文件: {path}")


def main():
    from tray_app import main as tray_main
    tray_main()


if __name__ == "__main__":
    main()
