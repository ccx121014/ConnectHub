@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist dist\ConnectHub-Server\ConnectHub-Server.exe (
    start "" "dist\ConnectHub-Server\ConnectHub-Server.exe"
    goto :eof
)

if exist ConnectHub-Server.exe (
    start "" "ConnectHub-Server.exe"
    goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    if exist server\main.py (
        start "" python server\main.py
        goto :eof
    )
)

echo.
echo 无法启动 ConnectHub 服务器
echo.
echo 请先运行 Install-ConnectHub.bat 安装，或运行 build.bat 构建
echo.
pause
