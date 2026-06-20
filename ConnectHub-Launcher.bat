@echo off
REM ========================================================
REM ConnectHub 智能启动器（Windows）—— 双击此文件即可
REM 功能：
REM   1. 如果已构建了 exe，直接运行
REM   2. 如果有 Python 环境，用源码启动
REM   3. 没有 Python 时，提示用户安装（提供一键安装选项）
REM ========================================================

setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

title ConnectHub 智能启动器

:detect_exe

REM ---- 方式 A: 已打包的 exe ----
if exist ConnectHub-Client.exe (
    start "" ConnectHub-Client.exe
    goto :eof
)
if exist dist\ConnectHub-Client\ConnectHub-Client.exe (
    start "" dist\ConnectHub-Client\ConnectHub-Client.exe
    goto :eof
)

REM ---- 方式 B: 用 Python 源码启动 ----
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [信息] 检测到 Python 环境，正在启动 ConnectHub 客户端...
    if exist client\app.py (
        start "" python client\app.py
    ) else if exist ..\client\app.py (
        start "" python ..\client\app.py
    ) else (
        echo [错误] 找不到 client\app.py。请确认目录结构。
        pause
    )
    goto :eof
)

REM ---- 方式 C: 没有 Python ----
cls
echo ============================================================
echo                ConnectHub - 运行环境缺失
echo ============================================================
echo.
echo 您的电脑上没有安装 Python 环境。
echo 您可以选择以下方案：
echo.
echo   [1] 一键下载并安装 Python（推荐，自动）
echo   [2] 手动打开 Python 官网下载页
echo   [3] 退出
echo.
set /p choice="请输入选项 [1-3]: "

if "%choice%"=="1" goto :auto_install
if "%choice%"=="2" goto :manual_install
if "%choice%"=="3" goto :eof
goto :eof

:auto_install
echo.
echo [信息] 正在打开 Python 官网下载页，请下载并安装 Python 3.9 或更高版本。
echo        安装时请务必勾选 "Add Python to PATH"。
echo        安装完成后，请重新双击本文件 (ConnectHub-Launcher.bat)。
echo.
start "" "https://www.python.org/downloads/"
pause
goto :eof

:manual_install
echo.
echo 请访问 https://www.python.org/downloads/ 下载并安装 Python 3.9+。
echo 安装完成后重新双击本文件。
pause
start "" "https://www.python.org/downloads/"
goto :eof

endlocal
