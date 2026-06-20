@echo off
REM ========================================================
REM ConnectHub 一键安装程序（双击即可）
REM 功能：
REM   1. 自动检测并安装 Python（如果没有）
REM   2. 自动安装依赖包（PyQt5, websockets, pyinstaller）
REM   3. 自动构建 ConnectHub 客户端和服务器
REM   4. 在桌面创建快捷方式（双击即可运行）
REM   5. 在开始菜单创建入口
REM ========================================================

setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

title ConnectHub 一键安装

:: ==================== 配置 ====================
set "APP_NAME=ConnectHub"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PYTHON_INSTALLER=python-installer.exe"
set "INSTALL_DIR=%ProgramFiles%\ConnectHub"
set "DATA_DIR=%APPDATA%\ConnectHub"
set "DESKTOP_SHORTCUT=%USERPROFILE%\Desktop\ConnectHub.lnk"
set "STARTMENU_SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\ConnectHub.lnk"

:: ==================== 颜色定义 ====================
set "COLOR_GREEN=[92m"
set "COLOR_YELLOW=[93m"
set "COLOR_RED=[91m"
set "COLOR_BLUE=[94m"
set "COLOR_RESET=[0m"

:: ==================== 开始 ====================
cls
echo.
echo %COLOR_BLUE%=========================================%COLOR_RESET%
echo %COLOR_BLUE%    ConnectHub 一键安装程序                     %COLOR_RESET%
echo %COLOR_BLUE%=========================================%COLOR_RESET%
echo.
echo %COLOR_YELLOW%正在检查系统环境...%COLOR_RESET%
echo.

:: ========== 检查是否以管理员身份运行 ==========
fltmc >nul 2>&1 || (
    echo %COLOR_RED%需要管理员权限，正在重新启动...%COLOR_RESET%
    timeout /t 2 >nul
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: ========== 检查 Python ==========
:check_python
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
    echo %COLOR_GREEN%已检测到 Python %PY_VER%%COLOR_RESET%
    goto :install_deps
)

echo %COLOR_YELLOW%未检测到 Python，正在下载 Python %PYTHON_VERSION%...%COLOR_RESET%

:: 下载 Python 安装包
if exist "%PYTHON_INSTALLER%" del "%PYTHON_INSTALLER%"
powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing"
if not exist "%PYTHON_INSTALLER%" (
    echo %COLOR_RED%下载 Python 失败，请检查网络连接。%COLOR_RESET%
    echo 手动下载地址：%PYTHON_URL%
    pause
    exit /b 1
)

echo %COLOR_GREEN%Python 安装包下载完成，正在安装...%COLOR_RESET%
echo %COLOR_YELLOW%请在弹出的安装界面中勾选 "Add Python to PATH"！%COLOR_RESET%
echo.

:: 静默安装 Python（带 PATH）
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
if %ERRORLEVEL% NEQ 0 (
    echo %COLOR_YELLOW%静默安装失败，尝试交互式安装...%COLOR_RESET%
    "%PYTHON_INSTALLER%"
)

:: 清理安装包
if exist "%PYTHON_INSTALLER%" del "%PYTHON_INSTALLER%"

:: 重新检查 Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo %COLOR_RED%Python 安装失败，请手动安装。%COLOR_RESET%
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo %COLOR_GREEN%Python %PY_VER% 安装成功！%COLOR_RESET%
echo.

:: ========== 安装依赖 ==========
:install_deps
echo %COLOR_YELLOW%正在安装依赖包（PyQt5, websockets, pyinstaller）...%COLOR_RESET%
echo %COLOR_YELLOW%这可能需要几分钟，请耐心等待...%COLOR_RESET%
echo.

python -m pip install --upgrade pip >nul 2>&1
python -m pip install PyQt5 websockets pyinstaller >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo %COLOR_RED%依赖安装失败，请检查网络。%COLOR_RESET%
    pause
    exit /b 1
)

echo %COLOR_GREEN%依赖安装成功！%COLOR_RESET%
echo.

:: ========== 创建安装目录 ==========
echo %COLOR_YELLOW%正在创建安装目录...%COLOR_RESET%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

:: ========== 复制项目文件 ==========
echo %COLOR_YELLOW%正在复制程序文件...%COLOR_RESET%
xcopy /s /e /y /q "client" "%INSTALL_DIR%\client\" >nul
xcopy /s /e /y /q "server" "%INSTALL_DIR%\server\" >nul
xcopy /s /e /y /q "protocol" "%INSTALL_DIR%\protocol\" >nul
copy /y "version.json" "%INSTALL_DIR%\version.json" >nul
copy /y "client\config.json" "%INSTALL_DIR%\client\config.json" >nul
copy /y "server\config.json" "%INSTALL_DIR%\server\config.json" >nul

echo %COLOR_GREEN%文件复制完成！%COLOR_RESET%
echo.

:: ========== 打包 exe ==========
echo %COLOR_YELLOW%正在构建可执行程序...%COLOR_RESET%
echo %COLOR_YELLOW%这可能需要几分钟，请耐心等待...%COLOR_RESET%
echo.

cd /d "%INSTALL_DIR%"
if exist build rmdir /s /q build >nul
if exist dist rmdir /s /q dist >nul

:: 打包客户端
pyinstaller --noconfirm --clean "client\app.py" ^
    --name "ConnectHub-Client" ^
    --windowed ^
    --add-data "protocol;protocol" ^
    --add-data "version.json;." ^
    --add-data "client\config.json;." ^
    --hidden-import websockets ^
    --hidden-import PyQt5.QtCore ^
    --hidden-import PyQt5.QtGui ^
    --hidden-import PyQt5.QtWidgets >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo %COLOR_RED%客户端打包失败！%COLOR_RESET%
    pause
    exit /b 1
)

:: 打包服务器
pyinstaller --noconfirm --clean "server\main.py" ^
    --name "ConnectHub-Server" ^
    --console ^
    --add-data "protocol;protocol" ^
    --add-data "version.json;." ^
    --add-data "server\config.json;." ^
    --hidden-import websockets >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo %COLOR_RED%服务器打包失败！%COLOR_RESET%
    pause
    exit /b 1
)

:: 创建 data 目录
if not exist "%INSTALL_DIR%\dist\ConnectHub-Server\data" mkdir "%INSTALL_DIR%\dist\ConnectHub-Server\data"

echo %COLOR_GREEN%程序构建完成！%COLOR_RESET%
echo.

:: ========== 创建快捷方式 ==========
echo %COLOR_YELLOW%正在创建桌面快捷方式...%COLOR_RESET%

:: 删除旧快捷方式
if exist "%DESKTOP_SHORTCUT%" del "%DESKTOP_SHORTCUT%"
if exist "%STARTMENU_SHORTCUT%" del "%STARTMENU_SHORTCUT%"

:: 创建客户端快捷方式（桌面）
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $shortcut = $WshShell.CreateShortcut('%DESKTOP_SHORTCUT%'); $shortcut.TargetPath = '%INSTALL_DIR%\dist\ConnectHub-Client\ConnectHub-Client.exe'; $shortcut.WorkingDirectory = '%INSTALL_DIR%\dist\ConnectHub-Client'; $shortcut.Description = 'ConnectHub 客户端'; $shortcut.Save()"

:: 创建客户端快捷方式（开始菜单）
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $shortcut = $WshShell.CreateShortcut('%STARTMENU_SHORTCUT%'); $shortcut.TargetPath = '%INSTALL_DIR%\dist\ConnectHub-Client\ConnectHub-Client.exe'; $shortcut.WorkingDirectory = '%INSTALL_DIR%\dist\ConnectHub-Client'; $shortcut.Description = 'ConnectHub 客户端'; $shortcut.Save()"

echo %COLOR_GREEN%快捷方式创建完成！%COLOR_RESET%
echo.

:: ========== 完成 ==========
cls
echo.
echo %COLOR_GREEN%=========================================%COLOR_RESET%
echo %COLOR_GREEN%      ConnectHub 安装完成！                   %COLOR_RESET%
echo %COLOR_GREEN%=========================================%COLOR_RESET%
echo.
echo %COLOR_YELLOW%已创建以下内容：%COLOR_RESET%
echo.
echo   📁 程序目录: %INSTALL_DIR%\dist\ConnectHub-Client\
echo   📁 服务器目录: %INSTALL_DIR%\dist\ConnectHub-Server\
echo   🖼️ 桌面快捷方式: ConnectHub.lnk
echo   📂 开始菜单: ConnectHub
echo.
echo %COLOR_YELLOW%使用方法：%COLOR_RESET%
echo.
echo   1. 先启动服务器：
echo      打开 %INSTALL_DIR%\dist\ConnectHub-Server\ConnectHub-Server.exe
echo      （保持窗口开启）
echo.
echo   2. 启动客户端：
echo      双击桌面的「ConnectHub」快捷方式
echo.
echo   3. 登录时输入服务器地址和用户名即可使用！
echo.
echo %COLOR_YELLOW%服务器地址：%COLOR_RESET%
echo   - 同一局域网：服务器电脑的内网 IP（例如 192.168.1.100）
echo   - 外网：需要部署到云服务器或配置内网穿透
echo.
pause
exit /b 0
