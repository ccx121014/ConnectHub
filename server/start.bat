@echo off
REM ========================================================
REM ConnectHub 服务器启动脚本
REM ========================================================

setlocal
cd /d "%~dp0"

REM 优先运行已打包的 exe，否则用 Python 启动
if exist ConnectHub-Server.exe (
    ConnectHub-Server.exe
    goto :eof
)

REM 如果有上层 dist 目录（开发模式）
if exist ..\dist\ConnectHub-Server\ConnectHub-Server.exe (
    cd ..\dist\ConnectHub-Server
    ConnectHub-Server.exe
    goto :eof
)

REM 回退到 Python 源码模式
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未检测到 Python，也没有 ConnectHub-Server.exe。
    echo 请先安装 Python 3.9+ 或运行 build.bat 生成可执行程序。
    pause
    exit /b 1
)

cd /d "%~dp0\..\server" 2>nul
if exist main.py (
    python main.py
) else (
    echo [错误] 找不到 server/main.py 或 ConnectHub-Server.exe。
    pause
    exit /b 1
)
endlocal
