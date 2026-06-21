@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo     ConnectHub 安装包构建
echo ============================================
echo.

REM 检查 NSIS 是否存在
where makensis >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo 未检测到 NSIS，正在尝试通过 choco install nsis.portable ...
    where choco >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        choco install nsis.portable -y
    ) else (
        echo 请手动安装 NSIS: https://nsis.sourceforge.io/Download
        pause
        exit /b 1
    )
)

REM 检查 PyInstaller 产物
if not exist dist\ConnectHub-Client\ConnectHub-Client.exe (
    echo [错误] 未找到 dist\ConnectHub-Client\ConnectHub-Client.exe
    echo 请先运行 build.bat 构建程序
    pause
    exit /b 1
)
if not exist dist\ConnectHub-Server\ConnectHub-Server.exe (
    echo [错误] 未找到 dist\ConnectHub-Server\ConnectHub-Server.exe
    echo 请先运行 build.bat 构建程序
    pause
    exit /b 1
)

echo 正在编译安装器...
cd /d "%~dp0"
makensis installer\installer.nsi
if %ERRORLEVEL% NEQ 0 (
    echo 安装器编译失败
    pause
    exit /b 1
)

echo.
echo ============================================
echo          安装包构建完成: ConnectHub-Setup.exe
echo ============================================
echo.
echo 双击 ConnectHub-Setup.exe

if exist ConnectHub-Setup.exe (
    echo 位置: %~dp0ConnectHub-Setup.exe
    echo.
    echo 请将此文件分发给用户，用户双击即可安装。
)
pause
