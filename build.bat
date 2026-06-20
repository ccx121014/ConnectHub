@echo off
REM ========================================================
REM ConnectHub 一键构建脚本（Windows）
REM 功能：
REM   1. 检查并安装 Python / 依赖
REM   2. 打包客户端 (ConnectHub-Client.exe)
REM   3. 打包服务器 (ConnectHub-Server.exe)
REM   4. 生成发布目录 dist/
REM ========================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo       ConnectHub 一键构建 (Windows)
echo ============================================
echo.

REM === 1. 检查 Python ===
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未检测到 Python。
    echo 请先安装 Python 3.9+，下载地址：
    echo   https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo [信息] 已检测到 Python %PY_VER%
echo.

REM === 2. 安装依赖 ===
echo [1/3] 安装 / 更新依赖包 (PyQt5, websockets, pyinstaller) ...
python -m pip install --upgrade pip
python -m pip install PyQt5 websockets pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)
echo.

REM === 3. 清理旧构建产物 ===
echo [2/3] 清理旧构建产物 ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

REM === 4. 打包客户端 ===
echo [3/3] 打包 ConnectHub-Client ...
pyinstaller --noconfirm --clean build_client.spec
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 客户端打包失败。
    pause
    exit /b 1
)

REM === 5. 打包服务器 ===
echo.
echo [4/3] 打包 ConnectHub-Server ...
pyinstaller --noconfirm --clean build_server.spec
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 服务器打包失败。
    pause
    exit /b 1
)

REM === 6. 复制配置文件到发布目录 ===
echo.
echo [信息] 复制配置文件到发布目录 ...
if exist dist\ConnectHub-Client (
    copy /y client\config.json dist\ConnectHub-Client\config.json >nul
    copy /y version.json dist\ConnectHub-Client\version.json >nul
)
if exist dist\ConnectHub-Server (
    copy /y server\config.json dist\ConnectHub-Server\config.json >nul
    copy /y version.json dist\ConnectHub-Server\version.json >nul
    REM 服务器需要 data 目录以保存用户信息
    if not exist dist\ConnectHub-Server\data mkdir dist\ConnectHub-Server\data
)

echo.
echo ============================================
echo            构建完成！
echo ============================================
echo.
echo 客户端: %cd%\dist\ConnectHub-Client\ConnectHub-Client.exe
echo 服务器:   %cd%\dist\ConnectHub-Server\ConnectHub-Server.exe
echo.
echo 提示:
echo   - 客户端: 双击 ConnectHub-Client.exe 即可运行
echo   - 服务器: 双击 ConnectHub-Server.exe 启动服务，监听端口可在 config.json 中修改
echo   - 外网访问: 需要开放防火墙端口 +（可选）配置公网 IP / 内网穿透
echo.
pause
endlocal
