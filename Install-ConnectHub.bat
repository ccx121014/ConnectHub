@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================
echo     ConnectHub 一键安装程序
echo ============================================
echo.
echo [1/6] 检测环境...
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo 已检测到 Python
    goto install_deps
)

echo 未检测到 Python
echo.
echo [2/6] 正在下载 Python 安装程序...
echo.

powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python-installer.exe' -UseBasicParsing"
if not exist python-installer.exe (
    echo 下载失败，请手动安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 Add Python to PATH
    pause
    exit /b 1
)

echo [3/6] 正在安装 Python...
python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
if %ERRORLEVEL% NEQ 0 (
    echo 静默安装失败，请手动运行 python-installer.exe
    echo 安装时请勾选 Add Python to PATH
    pause
    exit /b 1
)

echo Python 安装完成
if exist python-installer.exe del python-installer.exe

:install_deps
echo.
echo [4/6] 正在安装依赖...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install PyQt5 websockets pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo 依赖安装失败，请检查网络
    pause
    exit /b 1
)
echo 依赖安装完成

echo.
echo [5/6] 正在构建程序...
cd /d "%~dp0"

pyinstaller --noconfirm --clean client/app.py --name ConnectHub-Client --windowed --add-data "protocol;protocol" --add-data "version.json;." --add-data "client/config.json;." --hidden-import websockets --hidden-import PyQt5.QtCore --hidden-import PyQt5.QtGui --hidden-import PyQt5.QtWidgets
if %ERRORLEVEL% NEQ 0 (
    echo 客户端构建失败
    pause
    exit /b 1
)

pyinstaller --noconfirm --clean server/main.py --name ConnectHub-Server --console --add-data "protocol;protocol" --add-data "version.json;." --add-data "server/config.json;." --hidden-import websockets
if %ERRORLEVEL% NEQ 0 (
    echo 服务器构建失败
    pause
    exit /b 1
)

if not exist dist\ConnectHub-Server\data mkdir dist\ConnectHub-Server\data

echo 构建完成

echo.
echo [6/6] 正在创建桌面快捷方式...
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\ConnectHub.lnk'); $shortcut.TargetPath = '%~dp0dist\ConnectHub-Client\ConnectHub-Client.exe'; $shortcut.WorkingDirectory = '%~dp0dist\ConnectHub-Client'; $shortcut.Description = 'ConnectHub 客户端'; $shortcut.Save()"

echo.
echo ============================================
echo           ConnectHub 安装完成
echo ============================================
echo.
echo 客户端: %~dp0dist\ConnectHub-Client\ConnectHub-Client.exe
echo 服务器: %~dp0dist\ConnectHub-Server\ConnectHub-Server.exe
echo 桌面快捷方式: ConnectHub.lnk
echo.
echo 使用步骤:
echo   1. 先启动服务器: 双击 ConnectHub-Server.exe 并保持窗口开启
echo   2. 再启动客户端: 双击桌面快捷方式 ConnectHub
echo   3. 登录时输入: 服务器地址=服务器电脑IP, 端口=8765, 用户名=自取
echo.
pause
