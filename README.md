# ConnectHub

一款集**即时聊天、文件传输、远程桌面**于一体的协同工具。

---

## 🚀 最快上手（完全不用命令行）

### 方式一：一键安装（推荐）

1. 下载本项目源码并解压
2. **右键** `Install-ConnectHub.bat` → **以管理员身份运行**
3. 等待安装完成（自动安装 Python + 依赖 + 构建程序）
4. 桌面上会出现「ConnectHub」快捷方式，**双击即可运行**

### 方式二：下载预编译版本

访问 Release 页面：https://github.com/ccx121014/ConnectHub/releases

下载 `ConnectHub-Client.zip` 和 `ConnectHub-Server.zip`，解压后双击运行。

---

## 💡 使用方法

### 启动服务器（只需一台电脑）

1. **双击** `ConnectHub-Server.exe`
2. 窗口显示 `Starting WebSocket server on 0.0.0.0:8765`
3. **保持窗口开启**，不要关闭

### 启动客户端（每位用户）

1. **双击** `ConnectHub-Client.exe`
2. 在登录界面输入：
   - **服务器**: 服务器电脑的 IP（局域网用内网 IP，外网用公网 IP）
   - **端口**: `8765`
   - **用户名**: 自取
3. 点击「连接」进入主界面

### 使用功能

| 功能 | 操作 |
|---|---|
| 💬 聊天 | 双击左侧联系人 |
| 📁 文件传输 | 点击联系人右侧的 📁 按钮 |
| 🖥 远程桌面 | 点击联系人右侧的 🖥 按钮 |

---

## 🌍 外网连接

默认只能在同一局域网使用。要跨网络使用：

1. **最简单**：租一台云服务器（阿里云/腾讯云），在上面运行服务器，安全组放行 8765 端口
2. **零成本**：使用 ZeroTier 虚拟局域网（https://www.zerotier.com/）
3. **家庭宽带**：路由器端口映射（需有公网 IP）

---

## 📁 文件说明

```
ConnectHub/
├── Install-ConnectHub.bat    ← 一键安装（管理员运行）
├── Start-Client.bat          ← 启动客户端（双击）
├── Start-Server.bat          ← 启动服务器（双击）
├── build.bat                 ← 开发者一键构建脚本
├── dist/
│   ├── ConnectHub-Client/
│   │   └── ConnectHub-Client.exe   ← 客户端（双击运行）
│   └── ConnectHub-Server/
│       └── ConnectHub-Server.exe   ← 服务器（双击运行）
├── client/                   ← 客户端源码
├── server/                   ← 服务器源码
└── protocol/                 ← 通信协议
```

---

## ❓ 常见问题

**Q: 双击后没反应？**
A: 请确认已完整解压整个目录，不要只拖出单个 exe 文件。

**Q: 提示无法连接？**
A: 检查服务器是否在运行，服务器地址是否正确，防火墙是否放行 8765 端口。

**Q: 没有 Python 怎么办？**
A: 运行 `Install-ConnectHub.bat`（管理员）自动安装，或手动安装后运行 `build.bat`。

**Q: Release 页面没有下载文件？**
A: 由于 GitHub Actions 上传步骤问题，目前需要自行构建。运行 `Install-ConnectHub.bat` 即可自动完成。

---

## 🛡 安全提示

ConnectHub 为信任的小团队设计。部署在公网时建议设置复杂密码并限制端口访问。

