@echo off
REM ========================================================
REM ConnectHub 客户端启动器（双击即运行）
REM 智能检测：优先用已打包的 exe，没有则用 Python 源码，都没有则提示安装
REM ========================================================

setlocal enabledelayedexpansion
chcp 65001 >nul

:: 尝试运行已打包的 exe
if exist "%~dp0ConnectHub-Client.exe" (
    start "" "%~dp0ConnectHub-Client.exe"
    goto :eof
)

:: 尝试运行 dist 目录中的 exe
if exist "%~dp0dist\ConnectHub-Client\ConnectHub-Client.exe" (
    start "" "%~dp0dist\ConnectHub-Client\ConnectHub-Client.exe"
    goto :eof
)

:: 尝试用 Python 运行源码
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    if exist "%~dp0client\app.py" (
        start "" python "%~dp0client\app.py"
        goto :eof
    )
)

:: 都不行，提示安装
cls
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║           ConnectHub - 运行环境缺失             ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo 您的电脑上没有安装 Python 或未构建程序。
echo.
echo 解决方案：
echo.
echo 方案一：下载预编译版本（推荐）
echo   访问 https://github.com/ccx121014/ConnectHub/releases
echo   下载 ConnectHub-Client.zip，解压后双击 ConnectHub-Client.exe
echo.
echo 方案二：一键安装
echo   运行 Install-ConnectHub.bat（需要管理员权限）
echo   自动安装 Python + 依赖 + 构建程序
echo.
echo 方案三：手动安装 Python
echo   下载地址：https://www.python.org/downloads/
echo   安装后运行 build.bat 构建程序
echo.
pause
start "" "https://github.com/ccx121014/ConnectHub/releases"
