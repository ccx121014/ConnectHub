# ConnectHub 使用指南（用户/管理员必读）

ConnectHub 是一款集**即时聊天、文件传输、远程桌面**于一体的协同工具。

---

## 📦 方案一：最简单（推荐普通用户）—— 双击运行（免装 Python）

### 1. 下载并解压

在 GitHub Releases 页面下载 `ConnectHub-Client.zip`（和 `ConnectHub-Server.zip`，如果您要部署服务器），解压到任意目录，例如：

```
C:\ConnectHub\
├── ConnectHub-Client\         ← 客户端
│   ├── ConnectHub-Client.exe  ← 双击运行
│   ├── config.json            ← 服务器地址配置
│   └── ...
└── ConnectHub-Server\         ← 服务器（部署到一台电脑）
    ├── ConnectHub-Server.exe  ← 双击启动
    ├── config.json
    └── data\
```

### 2. 先启动一台服务器（只需一个人操作）

1. 在 **一台公共电脑**（或公网服务器）上，进入 `ConnectHub-Server\` 目录
2. **双击** `ConnectHub-Server.exe`
3. 会显示类似 `Starting WebSocket server on 0.0.0.0:8765` 的信息，**保持窗口开启**
4. 查看本机 IP 地址：按 `Win + R` → 输入 `cmd` → 回车 → 执行 `ipconfig`，找到 `IPv4 地址`
   （例如 `192.168.1.100`）
5. 告诉所有朋友：**服务器地址是 192.168.1.100，端口 8765**

> ⚠️ 服务器窗口关闭后，其他人将无法连接。请保持该窗口打开，或设为开机自启。

### 3. 每位用户启动客户端

1. 进入 `ConnectHub-Client\` 目录
2. **双击** `ConnectHub-Client.exe`
3. 在登录界面：
   - **服务器**: 填入服务器电脑的 IP（例如 `192.168.1.100`，外网使用公网 IP）
   - **端口**: `8765`（如服务器改了端口请同步修改）
   - **用户名**: 自取（例如 `小明`、`alice`）
   - **密码**（可选）：留空即可
4. 点击 **连接**（首次注册用户可点 **注册**）
5. 成功进入后，即可看到其他在线用户

### 4. 使用三大功能

- **聊天**: 在左侧双击某个联系人，打开聊天窗口发送消息
- **文件传输**: 在联系人右侧点击 **📁** 按钮，或切到 "文件传输" 标签页，选择文件发送
- **远程桌面**: 在联系人右侧点击 **🖥** 按钮请求共享，对方同意后即可看到对方桌面

---

## 🔧 方案二：从源码构建（开发者 / 需要自定义）

### 一次性准备（约 5 分钟）

1. 安装 Python 3.9 或更高版本：https://www.python.org/downloads/
   - 安装时**务必勾选** `Add Python to PATH`
2. 下载本项目源码并解压

### 一键打包 exe

```bat
cd C:\path\to\ConnectHub
build.bat
```

脚本会自动：

- 安装 `PyQt5` / `websockets` / `pyinstaller` 依赖
- 打包客户端 `ConnectHub-Client.exe`
- 打包服务器 `ConnectHub-Server.exe`
- 生成产物在 `dist\` 目录

打包完成后，把 `dist\ConnectHub-Client\` 整个目录 **压缩为 ZIP** 分发给用户即可，
用户 **不需要** 安装 Python。

### 开发模式运行（不打包）

```bat
cd C:\path\to\ConnectHub
REM 启动服务器
cd server
python main.py

REM （另开一个 cmd 窗口）启动客户端
cd client
python app.py
```

或者直接双击根目录的 `ConnectHub-Launcher.bat` 也可以启动客户端。

---

## 🌍 外网 / 跨网络连接

默认情况下 ConnectHub 只能在**同一局域网**内使用。要让外网用户连进来，有三种方案：

### 方案 A：使用有公网 IP 的服务器（最简单，推荐）

1. 租用一台云服务器（阿里云 / 腾讯云 / AWS 等，最便宜只要几十元/月）
2. 在云服务器上运行 `ConnectHub-Server.exe`
3. 在云服务器的 **安全组/防火墙** 中放行 TCP 端口 `8765`
4. 用户登录时 **服务器** 处填入云服务器的公网 IP（例如 `120.xx.xx.xx`）
5. 就可以跨网络使用了！

### 方案 B：内网穿透（frp / ngrok / ZeroTier）

如果没有云服务器，可以把家里的电脑通过内网穿透暴露到外网：

- **ZeroTier**（最简单，P2P 虚拟局域网）：https://www.zerotier.com/
  - 所有参与的电脑都装 ZeroTier 客户端，加入同一个网络
  - 服务器启动时使用 ZeroTier 分配的 IP
- **frp**（需一台公网中转机）：https://github.com/fatedier/frp
- **ngrok**：https://ngrok.com/

### 方案 C：路由器端口映射（家庭宽带 + 公网 IP）

1. 确认宽带有公网 IP（可在 `ip138.com` 查看）
2. 进入路由器管理页面（通常是 `192.168.1.1`）
3. 找到 "端口转发" / "虚拟服务器"
4. 新增规则：外部端口 `8765` → 服务器电脑内网 IP 的 `8765` 端口
5. 用户连接时使用您的公网 IP

### 修改服务器端口

编辑 `ConnectHub-Server\config.json`：

```json
{
  "host": "0.0.0.0",
  "port": 8765
}
```

把 `port` 改成您想要的端口号，保存后重新启动服务器即可。

---

## 🔄 自动更新

- 客户端在登录成功后，会**异步检查** GitHub Release 上是否有新版本
- 发现新版本时会弹出提示框，点击 "去下载" 即可打开浏览器到下载页面
- 您也可以随时在 GitHub Releases 手动下载：
  https://github.com/ccx121014/ConnectHub/releases

如需关闭自动更新，编辑 `ConnectHub-Client\config.json`：

```json
{ "auto_update": false }
```

---

## 📁 项目文件说明

```
ConnectHub/
├── ConnectHub-Launcher.bat   ← 双击启动客户端（智能检测 Python / exe）
├── build.bat                 ← 一键构建脚本（打包 exe）
├── build_client.spec         ← PyInstaller 客户端配置
├── build_server.spec         ← PyInstaller 服务器配置
├── version.json              ← 版本信息（用于自动更新检查）
├── README.md                 ← 本文档
├── client/                   ← 客户端源码
│   ├── app.py                ← 客户端入口
│   ├── main_window.py        ← 主窗口
│   ├── contact_list.py       ← 联系人列表
│   ├── chat_widget.py        ← 聊天窗口
│   ├── websocket_client.py   ← WebSocket 通信
│   ├── updater.py            ← 自动更新检查器
│   ├── config.json           ← 客户端配置（服务器地址等）
│   └── start.bat             ← 客户端启动脚本
├── server/                   ← 服务器源码
│   ├── main.py               ← 服务器入口
│   ├── user_manager.py       ← 用户管理
│   ├── chat_history.py       ← 聊天记录
│   ├── config.json           ← 服务器配置（host/port 等）
│   └── start.bat             ← 服务器启动脚本
└── protocol/                 ← 通信协议
    └── messages.py           ← 消息格式定义
```

---

## ❓ 常见问题

**Q: 双击 exe 后闪退或报错 "缺少 ..."？**
A: 请确认已完整解压整个目录（不要只拖出 exe 文件），`ConnectHub-Client\` 下的所有文件都必须保留。

**Q: 提示 "无法连接到服务器"？**
A: 检查三点：
   1. 服务器电脑上的 `ConnectHub-Server.exe` 是否在运行
   2. 服务器地址是否正确（局域网用内网 IP，外网用公网 IP）
   3. 服务器电脑的防火墙是否放行 8765 端口

**Q: 文件传输只能传到同目录？**
A: 收到文件时会弹窗让您选择保存位置，您可以保存到任何地方。

**Q: 远程桌面画面很卡？**
A: 远程桌面目前每秒 2 帧（为了兼容弱网），建议在同一局域网内使用。

**Q: 如何设置开机自启？**
A: 把 `ConnectHub-Server.exe` 的快捷方式放到：
   `C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\`

---

## 🛡 安全提示

- ConnectHub 是为**信任的小团队**设计的工具，请勿在公网无防护地运行
- 如果部署在公网，建议：
  1. 设置复杂的用户名 + 密码
  2. 仅开放必要的端口
  3. 定期更新到最新版本

---

## 📝 License & Credits

- 界面使用 [PyQt5](https://www.riverbankcomputing.com/software/pyqt/)
- 实时通信使用 [websockets](https://github.com/python-websockets/websockets)
- 打包使用 [PyInstaller](https://pyinstaller.org/)

