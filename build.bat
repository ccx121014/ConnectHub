@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo       ConnectHub 一键构建
echo ============================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未检测到 Python
    echo 请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 Add Python to PATH
    pause
    exit /b 1
)

echo [1/3] 正在安装依赖...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install PyQt5 websockets pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 依赖安装失败，请检查网络
    pause
    exit /b 1
)
echo 依赖安装完成
echo.

echo [2/3] 正在构建客户端...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --noconfirm --clean client/app.py --name ConnectHub-Client --windowed --add-data "protocol;protocol" --add-data "version.json;." --add-data "client/config.json;." --hidden-import websockets --hidden-import PyQt5.QtCore --hidden-import PyQt5.QtGui --hidden-import PyQt5.QtWidgets
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 客户端构建失败
    pause
    exit /b 1
)
echo 客户端构建完成
echo.

echo [3/3] 正在构建服务器...
pyinstaller --noconfirm --clean server/main.py --name ConnectHub-Server --console --add-data "protocol;protocol" --add-data "version.json;." --add-data "server/config.json;." --hidden-import websockets
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 服务器构建失败
    pause
    exit /b 1
)
if not exist dist\ConnectHub-Server\data mkdir dist\ConnectHub-Server\data
echo 服务器构建完成
echo.

echo ============================================
echo          构建完成！
echo ============================================
echo.
echo 客户端: %~dp0dist\ConnectHub-Client\ConnectHub-Client.exe
echo 服务器:   %~dp0dist\ConnectHub-Server\ConnectHub-Server.exe
echo.
echo 使用方法:
echo   1. 双击 dist\ConnectHub-Server\ConnectHub-Server.exe 启动服务器
echo   2. 双击 dist\ConnectHub-Client\ConnectHub-Client.exe 启动客户端
echo   3. 登录时输入: 服务器地址=服务器IP, 端口=8765, 用户名=自取
echo.
pause
