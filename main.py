"""GitHub 每日签到工具 - 主入口"""

import sys

from ai_client import AIClient
from config_manager import interactive_setup, load_config
from content_generator import generate_content
from github_manager import GitHubManager


def run_checkin(dry_run=False, topic_name=None, count=1, on_article=None):
    """执行签到。
    topic_name: 指定主题名称，None 为随机。
    count: 生成文章数量。
    on_article: 可选回调 (filename, content)，每生成一篇文章后调用。
    """
    config = load_config()
    if not config:
        print("未找到配置，请先运行配置向导。")
        config = interactive_setup()
        if not config:
            return

    ai_cfg = config["ai"]
    client = AIClient(ai_cfg["base_url"], ai_cfg["api_key"], ai_cfg["model"])
    gm = GitHubManager(config["github"])

    if not dry_run:
        gm.ensure_repo()

    for i in range(count):
        if count > 1:
            print(f"\n===== 第 {i + 1}/{count} 篇 =====")
        print("\n正在生成今日内容...")
        filename, content, category, commit_msg = generate_content(client, topic_name=topic_name)
        print(f"生成完成: {filename} (分类: {category})")
        print(f"Commit 消息: {commit_msg}")
        print(f"内容长度: {len(content)} 字符")

        # 回调通知 GUI 显示文章预览
        if on_article:
            on_article(filename, content)

        if dry_run:
            path = gm.save_local_only(filename, content)
            print(f"\n[dry-run] 预览文件: {path}")
        else:
            print("\n准备推送到 GitHub...")
            path = gm.save_and_push(filename, content, commit_msg)
            print(f"\n签到完成！文件: {path}")


def test_connection():
    """测试 API 连接"""
    config = load_config()
    if not config:
        print("未找到配置，请先运行: python main.py config")
        return

    ai_cfg = config["ai"]
    client = AIClient(ai_cfg["base_url"], ai_cfg["api_key"], ai_cfg["model"])
    print(f"测试连接: {ai_cfg['provider']} / {ai_cfg['model']}")

    ok, msg = client.test_connection()
    if ok:
        print(f"连接成功！AI 回复: {msg}")
    else:
        print(f"连接失败: {msg}")


def main():
    if len(sys.argv) < 2:
        run_checkin()
        return

    cmd = sys.argv[1]
    if cmd == "config":
        interactive_setup()
    elif cmd == "--dry-run":
        run_checkin(dry_run=True)
    elif cmd == "test":
        test_connection()
    elif cmd == "schedule":
        from setup_schedule import setup_schedule
        setup_schedule()
    elif cmd == "tray":
        from gui_app import main as gui_main
        gui_main()
    elif cmd == "help":
        print("用法:")
        print("  python main.py            执行一次签到并推送")
        print("  python main.py --dry-run  只生成内容，不推送")
        print("  python main.py config     重新配置")
        print("  python main.py test       测试 API 连接")
        print("  python main.py schedule   配置本地定时任务")
        print("  python main.py tray       启动托盘后台服务")
        print("  python main.py help       显示帮助")
    else:
        print(f"未知命令: {cmd}，输入 'python main.py help' 查看帮助。")


if __name__ == "__main__":
    main()
