"""配置管理模块 - 交互式引导配置 AI API 和 GitHub 凭证"""

import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_PROVIDERS = {
    "1": {"name": "SiliconFlow", "base_url": "https://api.siliconflow.cn/v1", "default_model": "Pro/zai-org/GLM-4.7"},
    "2": {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    "3": {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"},
    "4": {"name": "自定义 (OpenAI 兼容格式)", "base_url": "", "default_model": ""},
}


def load_config():
    """加载配置文件，不存在则返回 None"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_config(config):
    """保存配置到文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"\n配置已保存到 {CONFIG_FILE}")


def setup_ai_config():
    """交互式配置 AI API"""
    print("\n===== AI 模型配置 =====")
    print("选择 AI 服务商：")
    for k, v in DEFAULT_PROVIDERS.items():
        print(f"  {k}. {v['name']}")

    choice = input("\n请输入编号 [1]: ").strip() or "1"
    provider = DEFAULT_PROVIDERS.get(choice, DEFAULT_PROVIDERS["1"])

    if choice == "4":
        base_url = input("请输入 API Base URL: ").strip()
        default_model = input("请输入模型名称: ").strip()
    else:
        base_url = provider["base_url"]
        print(f"API 地址: {base_url}")
        default_model = provider["default_model"]
        custom_model = input(f"模型名称 [{default_model}]: ").strip()
        if custom_model:
            default_model = custom_model

    api_key = input("请输入 API Key: ").strip()

    return {
        "provider": provider["name"] if choice != "4" else "自定义",
        "base_url": base_url,
        "model": default_model,
        "api_key": api_key,
    }


def setup_github_config():
    """交互式配置 GitHub"""
    print("\n===== GitHub 配置 =====")
    repo_url = input("请输入 GitHub 仓库地址 (HTTPS 或 SSH): ").strip()

    print("\n认证方式：")
    print("  1. SSH (已配置 SSH Key)")
    print("  2. HTTPS + Personal Access Token")
    auth_choice = input("请选择 [1]: ").strip() or "1"

    github_config = {"repo_url": repo_url, "auth_type": "ssh" if auth_choice == "1" else "https"}

    if auth_choice == "2":
        token = input("请输入 GitHub Personal Access Token: ").strip()
        github_config["token"] = token
        # 自动将 token 嵌入 URL
        if repo_url.startswith("https://github.com/"):
            github_config["repo_url_with_token"] = repo_url.replace(
                "https://github.com/", f"https://{token}@github.com/"
            )

    local_dir = input("本地仓库存放路径 [./repo]: ").strip() or "./repo"
    github_config["local_dir"] = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), local_dir))

    return github_config


def interactive_setup():
    """完整的交互式配置流程"""
    print("=" * 50)
    print("  GitHub 每日签到工具 - 初始化配置")
    print("=" * 50)

    ai_config = setup_ai_config()
    github_config = setup_github_config()

    config = {"ai": ai_config, "github": github_config}

    print("\n===== 配置预览 =====")
    print(f"AI 服务商: {ai_config['provider']}")
    print(f"模型: {ai_config['model']}")
    print(f"API Key: {ai_config['api_key'][:8]}...")
    print(f"GitHub 仓库: {github_config['repo_url']}")
    print(f"认证方式: {github_config['auth_type']}")
    print(f"本地目录: {github_config['local_dir']}")

    confirm = input("\n确认保存？[Y/n]: ").strip().lower()
    if confirm in ("", "y", "yes"):
        save_config(config)
        return config
    else:
        print("已取消。")
        return None


if __name__ == "__main__":
    interactive_setup()
