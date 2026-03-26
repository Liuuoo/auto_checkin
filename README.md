# GitHub 每日签到工具

自动生成技术文章并推送到 GitHub，保持每日 contribution 记录。支持 GUI 桌面应用，可开机自启、托盘常驻。

## 功能

- **AI 生成内容** — 支持 8 种技术主题（算法、Python 技巧、Web 开发、系统设计等），可指定主题或随机生成
- **自动推送** — 生成的文章自动 commit 并 push 到 GitHub 仓库
- **GUI 桌面应用** — tkinter 窗口界面，操作直观
- **系统托盘** — 关闭窗口后最小化到托盘，后台继续运行
- **定时签到** — 设置每日签到时间，自动执行
- **开机自启** — 一键配置，开机后自动以托盘模式启动
- **多厂商支持** — SiliconFlow、OpenAI、DeepSeek 及任何 OpenAI 兼容 API

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 首次配置

```bash
python main.py config
```

按提示配置 AI 服务商（API Key）和 GitHub 仓库信息。

### 启动 GUI 应用

```bash
python main.py tray
```

### 命令行模式

```bash
python main.py              # 执行一次签到
python main.py --dry-run    # 预览模式，不推送
python main.py test         # 测试 API 连接
python main.py config       # 重新配置
python main.py schedule     # 配置 Windows 定时任务
```

## GUI 界面

启动后显示桌面窗口，包含：

- **状态面板** — 运行状态、上次签到时间与结果、下次签到时间
- **签到选项** — 选择主题（随机/指定）、文章数量（1-10 篇）
- **操作按钮** — 立即签到 / 预览
- **设置区** — 签到时间、端口、开机自启、最小化到托盘
- **运行日志** — 实时日志输出

关闭窗口后程序最小化到系统托盘，双击托盘图标恢复窗口。

## 生成内容主题

| 主题 | 内容 |
|------|------|
| 算法题解 | 经典算法题分析与 Python 实现 |
| Python 技巧 | 高级特性与实用技巧 |
| 数据结构 | 经典数据结构 Python 实现 |
| 设计模式 | 设计模式 Python 实现 |
| Web 开发 | Web 开发技术文章 |
| 系统设计 | 系统架构设计文章 |
| 新技术介绍 | 新技术/工具介绍 |
| DevOps 实践 | 运维与 DevOps 实践 |

文件按 `年/月/日期-标题.md` 自动组织存放。

## 项目结构

```
├── main.py               # 主入口
├── gui_app.py             # GUI 桌面应用
├── ai_client.py           # AI API 客户端
├── content_generator.py   # 内容生成
├── github_manager.py      # Git 仓库操作
├── config_manager.py      # 配置管理
├── setup_schedule.py      # Windows 定时任务
├── requirements.txt       # 依赖
└── config.json            # 配置文件（自动生成，已 gitignore）
```

## 环境要求

- Python 3.8+
- Git
- Windows 10/11
