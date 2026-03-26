@echo off
echo ===== GitHub 每日签到工具 - 打包 =====
echo.

pip install pyinstaller >nul 2>&1

echo 正在打包...
pyinstaller --noconsole --onefile --name "GitHub签到工具" --clean gui_app.py

echo.
if exist "dist\GitHub签到工具.exe" (
    echo 打包成功！
    echo 输出文件: dist\GitHub签到工具.exe
) else (
    echo 打包失败，请检查错误信息。
)
pause
