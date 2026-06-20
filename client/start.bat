@echo off
REM ========================================================
REM ConnectHub 客户端启动脚本
REM ========================================================

setlocal
cd /d "%~dp0"

REM 优先运行已打包的 exe
if exist ConnectHub-Client.exe (
    ConnectHub-Client.exe
    goto :eof
)

REM 如果有上层 dist 目录（开发模式）
if exist ..\dist\ConnectHub-Client\ConnectHub-Client.exe (
    cd ..\dist\ConnectHub-Client
    ConnectHub-Client.exe
    goto :eof
)

REM 回退到 Python 源码模式
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未检测到 Python，也没有 ConnectHub-Client.exe。
    echo 请先安装 Python 3.9+ 或运行 build.bat 生成可执行程序。
    echo Python 下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

cd /d "%~dp0\..\client" 2>nul
if exist app.py (
    python app.py
) else (
    echo [错误] 找不到 client/app.py 或 ConnectHub-Client.exe。
    pause
    exit /b 1
)
endlocal
