# ConnectHub

> 一站式在线协作套件 — 即时聊天 · 文件传输 · 远程桌面

ConnectHub 是一款轻量级的实时协作工具，结合 WebSocket 与 WebRTC 技术，提供跨网络的即时通讯、文件传输与远程桌面控制能力。

## ✨ 核心功能

| 模块 | 功能 | 技术 |
|------|------|------|
| 💬 **Chat** | 点对点聊天、群组聊天、消息历史 | WebSocket + JSON |
| 📂 **File Transfer** | 大文件分块传输、断点续传 | WebRTC DataChannel |
| 🖥️ **Remote Desktop** | 屏幕共享、远程键鼠控制 | WebRTC Video + DataChannel |
| 🔓 **NAT Traversal** | 内置 ICE/STUN/TURN 内网穿透 | aiortc + 公共 STUN |

## 🏗️ 项目结构

```
ConnectHub/
├── protocol/           # 通信协议定义
│   └── messages.py     # 消息类型 & JSON 结构
├── server/             # Python asyncio 服务端
│   ├── main.py         # WebSocket 主服务
│   ├── user_manager.py # 用户会话管理
│   ├── chat_history.py # 聊天历史存储
│   ├── webrtc_signaling.py # WebRTC 信令
│   ├── file_handler.py # 文件传输处理
│   ├── ice_server.py   # ICE/STUN/TURN 服务
│   └── requirements.txt
├── client/             # PyQt5 桌面客户端
│   ├── app.py          # 应用入口
│   ├── main_window.py  # 主窗口
│   ├── websocket_client.py  # WebSocket 客户端
│   ├── chat_widget.py  # 聊天组件
│   ├── contact_list.py # 联系人列表
│   ├── login_dialog.py # 登录对话框
│   ├── file_transfer.py   # 文件传输管理
│   ├── file_transfer_widget.py # 文件传输 UI
│   ├── desktop_capture.py   # 屏幕捕获
│   ├── desktop_viewer.py    # 远程桌面显示
│   ├── desktop_control.py   # 远程控制
│   ├── remote_desktop_window.py # 远程桌面窗口
│   ├── nat_traversal.py # NAT 穿透管理
│   └── requirements.txt
└── .trae/               # Trae IDE 规格说明
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- PyQt5 (客户端)
- 支持 Windows / macOS / Linux

### 安装依赖

```bash
# 服务端
pip install -r server/requirements.txt

# 客户端
pip install -r client/requirements.txt
```

### 启动服务端

```bash
cd server
python main.py
# WebSocket 服务运行于: ws://0.0.0.0:8765
```

### 启动客户端

```bash
cd client
python app.py
```

在登录界面输入：
- **Server Address**: `ws://127.0.0.1:8765`（或远程服务器地址）
- **Username**: 任意用户名（简单认证）

## 🔧 技术栈

| 层 | 技术 |
|----|------|
| 服务端 | Python 3 + `asyncio` + `websockets` |
| 客户端 GUI | PyQt5 |
| P2P 传输 | `aiortc` (WebRTC) |
| NAT 穿透 | ICE / STUN / TURN |
| 消息协议 | JSON over WebSocket |

## 🔐 安全说明

- 当前认证为简单用户名模式，仅用于演示/局域网协作
- 生产环境请启用：
  - 用户密码哈希存储（bcrypt/argon2）
  - WSS (WebSocket over TLS)
  - 文件传输内容加密（AES-GCM）
  - 远程控制双向授权确认

## 📝 许可证

MIT License — 自由使用、修改与分发。
