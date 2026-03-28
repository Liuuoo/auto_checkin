# GitHub 每日签到工具

一个基于 Python 的 Windows 桌面应用，用来自动生成技术内容并提交到 GitHub，帮助持续维护每日 contribution 记录。

## 主要功能

- 支持 GUI 桌面界面，适合日常使用
- 支持立即签到和预览模式
- 支持定时自动签到
- 支持系统托盘常驻运行
- 支持开机自动启动
- 支持启动时后台静默运行，直接进入托盘
- 支持关闭窗口时最小化到托盘
- 支持多家 OpenAI 兼容模型服务商
- 支持将生成内容自动提交并推送到 GitHub 仓库

## 环境要求

- Windows 10/11
- Python 3.8+
- Git

## 安装依赖

```bash
py -3 -m pip install -r requirements.txt
```

## 首次配置

命令行初始化配置：

```bash
py -3 main.py config
```

也可以直接启动图形界面，在“配置”页填写：

- AI 服务商、Base URL、模型名、API Key
- GitHub 仓库地址
- 认证方式：SSH 或 HTTPS + Token
- 本地仓库目录

## 启动方式

启动图形界面：

```bash
py -3 main.py tray
```

静默启动并直接进入托盘：

```bash
py -3 gui_app.py --minimized
```

## 命令行用法

```bash
py -3 main.py              # 执行一次签到并推送
py -3 main.py --dry-run    # 仅生成内容，不推送
py -3 main.py test         # 测试 AI 连接
py -3 main.py config       # 重新配置
py -3 main.py schedule     # 配置 Windows 定时任务
py -3 main.py tray         # 启动桌面程序
py -3 main.py help         # 查看帮助
```

## 设置页说明

在“设置”页可以配置：

- 每日签到时间
- 本地状态页端口
- 开机自动启动
- 启动时后台静默运行（直接进入托盘）
- 关闭窗口时最小化到托盘

说明：

- 开启“开机自动启动”后，程序会写入当前用户的 Windows 启动项
- 如果同时开启“启动时后台静默运行”，则开机后不会弹出主窗口，而是直接在系统托盘中运行
- 如果只开启“开机自动启动”，则开机后会正常显示主窗口

## 打包

直接执行：

```bash
build.bat
```

打包完成后，可执行文件位于：

```text
dist\GitHubCheckinTool.exe
```

## 项目结构

```text
main.py                主入口
gui_app.py             GUI 桌面应用
config_manager.py      配置读写
ai_client.py           AI 接口封装
content_generator.py   内容生成逻辑
github_manager.py      Git/GitHub 操作
setup_schedule.py      Windows 定时任务配置
requirements.txt       项目依赖
build.bat              打包脚本
```
