@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist dist\ConnectHub-Client\ConnectHub-Client.exe (
    start "" "dist\ConnectHub-Client\ConnectHub-Client.exe"
    goto :eof
)

if exist ConnectHub-Client.exe (
    start "" "ConnectHub-Client.exe"
    goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    if exist client\app.py (
        start "" python client\app.py
        goto :eof
    )
)

echo.
echo 无法启动 ConnectHub 客户端
echo.
echo 请先运行 Install-ConnectHub.bat 安装，或运行 build.bat 构建
echo.
pause
