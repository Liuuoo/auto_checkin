"""本地定时任务配置（Windows 计划任务）"""

import os
import subprocess
import sys


def setup_schedule():
    """配置 Windows 计划任务"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable
    main_script = os.path.join(script_dir, "main.py")

    print("===== 定时任务配置 =====")
    print("  1. 创建每日定时任务")
    print("  2. 删除定时任务")
    print("  3. 查看任务状态")

    choice = input("\n请选择 [1]: ").strip() or "1"

    task_name = "GitHubDailyCheckin"

    if choice == "1":
        time_str = input("每天执行时间 (HH:MM) [09:00]: ").strip() or "09:00"

        # 创建批处理脚本
        bat_path = os.path.join(script_dir, "run_checkin.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(f'@echo off\n')
            f.write(f'cd /d "{script_dir}"\n')
            f.write(f'"{python_exe}" "{main_script}"\n')

        # 使用 schtasks 创建计划任务
        cmd = (
            f'schtasks /create /tn "{task_name}" '
            f'/tr "{bat_path}" '
            f"/sc daily /st {time_str} /f"
        )
        print(f"\n执行: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"\n定时任务创建成功！")
            print(f"任务名: {task_name}")
            print(f"执行时间: 每天 {time_str}")
            print(f"脚本: {bat_path}")
        else:
            print(f"\n创建失败: {result.stderr}")
            print("提示: 可能需要以管理员权限运行。")

    elif choice == "2":
        cmd = f'schtasks /delete /tn "{task_name}" /f'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("定时任务已删除。")
        else:
            print(f"删除失败: {result.stderr}")

    elif choice == "3":
        cmd = f'schtasks /query /tn "{task_name}" /v /fo list'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print("未找到定时任务。")


if __name__ == "__main__":
    setup_schedule()
