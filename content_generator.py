"""内容生成模块 - 随机主题选择、提示词构造、内容生成"""

import random
import re
from datetime import datetime

TOPICS = [
    {
        "category": "algorithm",
        "name": "算法题解",
        "ext": ".md",
        "prompt": "请写一道经典算法题的详细解析和Python实现代码。要求：\n1. 题目描述\n2. 思路分析\n3. 完整的Python代码实现（含注释）\n4. 时间和空间复杂度分析\n请选择一道有趣的题目，如动态规划、图论、贪心、回溯等方向。代码中用注释说明关键步骤。",
    },
    {
        "category": "python_tips",
        "name": "Python 技巧",
        "ext": ".md",
        "prompt": "请介绍一个实用的Python编程技巧或高级特性，并给出完整的示例代码。要求：\n1. 技巧名称和简介（用注释）\n2. 使用场景说明\n3. 完整可运行的示例代码\n4. 最佳实践建议\n可以涉及：装饰器、生成器、上下文管理器、元编程、并发、类型提示等。",
    },
    {
        "category": "web_dev",
        "name": "Web 开发",
        "ext": ".md",
        "prompt": "请写一篇关于Web开发技术的技术文章。要求：\n1. 选择一个具体的Web开发主题（如RESTful API设计、WebSocket、CSS布局技巧、前端框架对比等）\n2. 包含概念介绍、实际代码示例、最佳实践\n3. 使用Markdown格式\n4. 内容深入实用",
    },
    {
        "category": "system_design",
        "name": "系统设计",
        "ext": ".md",
        "prompt": "请写一篇系统设计相关的技术文章。要求：\n1. 选择一个系统设计主题（如缓存策略、消息队列、负载均衡、数据库分片、微服务架构等）\n2. 包含设计思路、架构图描述、关键决策分析\n3. 使用Markdown格式\n4. 结合实际场景",
    },
    {
        "category": "new_tech",
        "name": "新技术介绍",
        "ext": ".md",
        "prompt": "请写一篇介绍某项编程领域新技术或工具的文章。要求：\n1. 技术/工具名称及背景\n2. 核心特性和优势\n3. 快速上手示例\n4. 使用Markdown格式\n可以涉及：Rust、Go、Zig、Bun、Deno、HTMX、Tauri、AI编程工具等方向。",
    },
    {
        "category": "data_structure",
        "name": "数据结构",
        "ext": ".md",
        "prompt": "请实现一个经典数据结构的Python版本，并配有详细讲解。要求：\n1. 数据结构名称和原理说明（用注释）\n2. 完整的Python类实现\n3. 使用示例和测试代码\n4. 复杂度分析\n可以选择：红黑树、B树、跳表、Trie、并查集、线段树、LRU Cache等。",
    },
    {
        "category": "design_pattern",
        "name": "设计模式",
        "ext": ".md",
        "prompt": "请用Python实现一个经典设计模式，并详细讲解。要求：\n1. 模式名称和适用场景（用注释）\n2. 完整的Python代码实现\n3. 使用示例\n4. 优缺点分析\n可以选择：观察者、策略、工厂、单例、装饰器、命令、状态机等模式。",
    },
    {
        "category": "devops",
        "name": "DevOps 实践",
        "ext": ".md",
        "prompt": "请写一篇关于DevOps/运维实践的技术文章。要求：\n1. 选择具体主题（Docker最佳实践、CI/CD流水线、K8s入门、监控告警、日志管理等）\n2. 包含实际配置或脚本示例\n3. 使用Markdown格式\n4. 注重实战经验",
    },
]


def get_topic_names():
    """返回所有可用主题名称列表"""
    return [t["name"] for t in TOPICS]


def get_topic_by_name(name):
    """按名称查找主题，找不到返回 None"""
    for t in TOPICS:
        if t["name"] == name:
            return t
    return None


def generate_content(ai_client, topic_name=None):
    """生成今日内容，返回 (filename, content, category, commit_msg)。
    topic_name: 指定主题名称，为 None 则随机选择。
    """
    if topic_name:
        topic = get_topic_by_name(topic_name) or random.choice(TOPICS)
    else:
        topic = random.choice(TOPICS)
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"今日主题: {topic['name']}")

    # 生成内容
    messages = [
        {
            "role": "system",
            "content": (
                "你是一位资深软件工程师和技术博主。请直接输出内容，不要包含多余的开场白。"
                "确保内容高质量、有深度、可读性强。"
            ),
        },
        {"role": "user", "content": topic["prompt"]},
    ]

    content = ai_client.chat(messages)

    # 从内容中提取标题
    title = _extract_title(content, topic)
    # 清理标题作为文件名
    safe_title = _sanitize_filename(title)
    filename = f"{today}-{safe_title}{topic['ext']}"

    # 让 AI 生成 commit 消息
    commit_msg = _generate_commit_message(ai_client, content, topic)

    return filename, content, topic["category"], commit_msg


def _generate_commit_message(ai_client, content, topic):
    """让 AI 根据生成的内容生成一条简洁的 commit 消息"""
    preview = content[:500]
    messages = [
        {
            "role": "system",
            "content": "你是一个 Git commit message 生成器。请根据内容生成一条简洁的中文 commit message，格式为：'docs: 简要中文描述'。只输出这一行，不要任何额外文字。",
        },
        {
            "role": "user",
            "content": f"主题类别: {topic['name']}\n\n内容摘要:\n{preview}",
        },
    ]
    try:
        msg = ai_client.chat(messages, max_tokens=60, temperature=0.3)
        return msg.strip().strip('"').strip("'")
    except Exception:
        return f"docs: add {topic['name']} article"


def _extract_title(content, topic):
    """从生成的内容中提取标题"""
    lines = content.strip().split("\n")
    for line in lines[:5]:
        line = line.strip()
        # Markdown 标题
        if line.startswith("#"):
            return line.lstrip("#").strip()
        # Python 注释标题
        if line.startswith('"""') or line.startswith("'''"):
            return line.strip("\"'").strip()
        if line.startswith("# ") and not line.startswith("# -"):
            cleaned = line.lstrip("# ").strip()
            if len(cleaned) > 2:
                return cleaned
    return topic["name"]


def _sanitize_filename(title):
    """将标题转为安全的文件名"""
    title = re.sub(r'[<>:"/\\|?*]', "", title)
    title = title.replace(" ", "-")
    title = re.sub(r"-+", "-", title)
    title = title.strip("-")
    return title[:50] if title else "daily"
