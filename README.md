# ConnectHub

即时聊天 · 文件传输 · 远程桌面（查看 + 控制）

---

## 🚀 一键下载安装（普通用户看这里）

### 方案一：下载安装包（推荐）

1. 打开 Release 页面：https://github.com/ccx121014/ConnectHub/releases
2. 下载 **`ConnectHub-Setup.exe`**
3. **双击** `ConnectHub-Setup.exe` 运行安装程序
4. 按提示点击「下一步」，选择安装目录
5. 安装完成后，桌面会出现两个图标：
   - **ConnectHub 客户端**（双击启动，用户日常使用）
   - **ConnectHub 服务器**（双击启动，只需在一台电脑上运行）
6. 可以在"设置 → 应用"里找到 ConnectHub，支持一键卸载

### 方案二：本地一键构建（开发者）

```bat
cd C:\path\to\ConnectHub
build-installer.bat
```

完成后双击 `ConnectHub-Setup.exe` 即可安装。

---

## 💡 使用方法

### 先启动服务器（任意一台电脑即可）

- **双击**桌面的「ConnectHub 服务器」
- 保持窗口开启，不要关闭
- 默认端口 **8765**

### 每位用户启动客户端

- **双击**桌面的「ConnectHub 客户端」
- 在登录界面输入：
  - **服务器**: 服务器电脑的 IP（局域网用内网 IP，外网用公网 IP）
  - **端口**: `8765`
  - **用户名**: 自取
  - **密码**: 任意（当前版本服务端不校验密码）
- 点击「连接」即可使用

### 功能使用

| 功能 | 操作 |
|---|---|
| 聊天 | 双击左侧联系人，输入消息发送 |
| 文件传输 | 切换到「文件传输」标签页，选择目标用户 → 选择文件并发送 |
| 远程桌面（查看） | 切换到「远程桌面」标签页，选择目标用户 → 点击「请求共享屏幕」 |
| 远程桌面（控制） | 对方接受后，直接在画面上操作鼠标 / 键盘即可控制对方电脑 |

### 远程桌面控制说明

- **查看**：A 请求共享 → B 接受 → B 的屏幕画面实时传给 A
- **控制**：A 在画面上移动鼠标 / 点击 / 按键 → 操作会发送到 B 端执行
- **权限开关**：B 端顶部有「允许远程控制」复选框，默认开启，可随时关闭拒绝对方控制
- **画质**：1280×720 分辨率、JPEG quality 82、约 8 fps、LANCZOS 缩放
- **平台限制**：控制执行仅 Windows 可用（依赖 Win32 API）；查看功能跨平台
- **安全提示**：远程控制功能强大，请只对信任的联系人开启

---

## 🌍 外网连接

默认仅能在同一局域网内使用。如需跨网络：

1. **最简单**：租用云服务器（阿里云/腾讯云/华为云），在上面运行 ConnectHub 服务器，安全组放行 8765 端口。用户连接时填入服务器公网 IP。
2. **零成本**：使用 ZeroTier 虚拟局域网（https://www.zerotier.com/），所有电脑加入同一个 ZeroTier 网络。
3. **家庭宽带**：路由器端口映射 + 公网 IP，将 8765 端口映射到服务器电脑。

---

## 🛠 开发与自行打包

### 目录结构

```
ConnectHub/
├── ConnectHub-Setup.exe       ← 安装包（构建后出现）
├── build-installer.bat        ← 一键构建安装包
├── build.bat                  ← 仅打包 exe（不生成安装器）
├── installer/
│   ├── installer.nsi          ← NSIS 安装器脚本
│   └── license.txt            ← 安装向导中的许可证文本
├── client/                    ← 客户端源码（tkinter）
│   ├── app.py                 ← 应用入口
│   ├── main_window.py         ← 主窗口（聊天/文件/桌面标签页）
│   ├── websocket_client.py    ← WebSocket 客户端
│   ├── contact_list.py        ← 联系人列表
│   ├── chat_widget.py         ← 聊天标签页
│   ├── file_transfer.py       ← 文件传输管理
│   ├── login_dialog.py        ← 登录对话框
│   ├── updater.py             ← 自动更新（检查 GitHub Releases）
│   ├── input_executor.py      ← 远程控制输入执行（Win32 API）
│   ├── ssl_stub.py            ← SSL 兼容层（PyInstaller 用）
│   ├── start.bat              ← 客户端启动脚本
│   ├── config.json            ← 客户端配置
│   └── requirements.txt       ← 客户端依赖
├── server/                    ← 服务器源码
│   ├── main.py                ← WebSocket 服务器主程序
│   ├── gui.py                 ← 服务器 GUI
│   ├── user_manager.py        ← 用户管理
│   ├── chat_history.py        ← 聊天记录持久化
│   ├── webrtc_signaling.py    ← WebRTC 信令服务
│   ├── start.bat              ← 服务器启动脚本
│   ├── config.json            ← 服务器配置
│   └── requirements.txt       ← 服务器依赖
├── protocol/                  ← 通信协议
│   ├── messages.py            ← 消息类型与序列化
│   └── signals.py             ← 纯 Python 信号系统
├── version.json               ← 版本信息
└── .github/workflows/
    └── build.yml              ← GitHub Actions 自动构建
```

### 依赖

- **客户端运行依赖**（已随安装包打包，无需手动安装）：
  - Python 3.9+
  - websockets
  - Pillow（屏幕捕获与显示）
- **服务器运行依赖**：Python 3.9+ + websockets
- **构建依赖**：Python 3.9+、PyInstaller、NSIS（通过 choco 自动安装）

### 构建完整流程（Windows）

1. 安装 Python 3.9+（勾选 Add Python to PATH）
2. 在项目目录运行 `build-installer.bat`
3. 自动完成：
   - 安装 websockets / Pillow / pyinstaller
   - 安装 NSIS（通过 choco）
   - 用 PyInstaller 打包客户端和服务器
   - 用 NSIS 编译安装器
4. 最终产物：`ConnectHub-Setup.exe`

---

## ❓ 常见问题

**Q: 双击安装包没反应？**
A: 请确认 Windows 允许运行外部应用，右键 → 属性 → 解除锁定。

**Q: 提示无法连接服务器？**
A: 检查 ConnectHub 服务器.exe 是否在运行，服务器地址是否正确，防火墙是否放行 8765 端口。若服务器在本机，可尝试用 `127.0.0.1` 代替 `localhost`。

**Q: 联系人列表不显示新上线的用户？**
A: v1.4.16+ 已修复此问题（服务端会在用户上线时向其他在线用户广播）。请确认双方都升级到 v1.4.16 或更高版本。

**Q: 远程桌面控制没反应？**
A: 检查被控方是否勾选了「允许远程控制」复选框；确认被控方运行在 Windows 上（其他平台暂不支持控制执行，只能查看）。

**Q: 登出后主窗口没关闭？**
A: v1.4.16+ 已修复此问题。请升级到最新版本。

**Q: 如何卸载？**
A: 打开"设置 → 应用 → ConnectHub → 卸载"，或运行安装目录下的 `Uninstall.exe`。

**Q: Release 页面没有下载文件？**
A: Release 页面的安装包由 GitHub Actions 自动构建，一般 5-10 分钟后出现。如果构建失败，可以本地运行 `build-installer.bat` 自行构建。

**Q: 老版本会自动更新吗？**
A: 客户端内置更新检查（通过 GitHub Releases API）。打开客户端后点击「检查更新」按钮即可。注意：跨大版本升级建议先卸载旧版再安装新版。

---

## 📋 版本历史

| 版本 | 主要改动 |
|------|----------|
| v1.4.17 | 远程桌面控制（鼠标+键盘）、画质优化（720p/82%/8fps/LANCZOS） |
| v1.4.16 | 修复新用户上线不显示、登出不关闭主窗口 |
| v1.4.15 | 内置 Pillow，屏幕共享开箱即用 |
| v1.4.14 | 修复重入风险、心跳泄露、登出崩溃 |
| v1.4.13 | 修复连接成功后自动关闭（set_status 缺失） |
| v1.4.12 | 修复 websocket_client start() AttributeError |
| v1.4.11 | 认证成功后初始化主窗口加异常保护 |
| v1.4.10 | 修复密码硬编码为空 |
| v1.4.9 | IPv4/IPv6 连接回退 |
| v1.4.8 及更早 | PyInstaller 模块排除修复、CI/CD 流程搭建 |

---

## 🛡 安全提示

ConnectHub 为小团队协作设计。部署在公网时请设置复杂密码并限制端口访问。远程控制功能权限较大，请仅对信任的联系人开启「允许远程控制」。
