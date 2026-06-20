@echo off
REM ========================================================
REM ConnectHub 服务器启动器（双击即运行）
REM ========================================================

setlocal enabledelayedexpansion
chcp 65001 >nul

if exist "%~dp0ConnectHub-Server.exe" (
    start "" "%~dp0ConnectHub-Server.exe"
    goto :eof
)

if exist "%~dp0dist\ConnectHub-Server\ConnectHub-Server.exe" (
    start "" "%~dp0dist\ConnectHub-Server\ConnectHub-Server.exe"
    goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    if exist "%~dp0server\main.py" (
        start "" python "%~dp0server\main.py"
        goto :eof
    )
)

cls
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║         ConnectHub 服务器 - 运行环境缺失         ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo 请先运行 Install-ConnectHub.bat 安装环境，
echo 或从 https://github.com/ccx121014/ConnectHub/releases 下载预编译版本。
echo.
pause
start "" "https://github.com/ccx121014/ConnectHub/releases"
