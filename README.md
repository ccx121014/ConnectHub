# ConnectHub

即时聊天 · 文件传输 · 远程桌面

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
- 点击「连接」即可使用

### 功能使用

| 功能 | 操作 |
|---|---|
| 聊天 | 双击左侧联系人 |
| 文件传输 | 点击联系人右侧的文件传输按钮 |
| 远程桌面 | 点击联系人右侧的远程桌面按钮 |

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
├── client/                    ← 客户端源码
├── server/                    ← 服务器源码
├── protocol/                  ← 通信协议
├── dist/                      ← PyInstaller 产物（运行 build.bat 后）
│   ├── ConnectHub-Client/
│   └── ConnectHub-Server/
└── .github/workflows/
    └── build.yml              ← GitHub Actions 自动构建
```

### 构建完整流程（Windows）

1. 安装 Python 3.9+（勾选 Add Python to PATH）
2. 在项目目录运行 `build-installer.bat`
3. 自动完成：
   - 安装 PyQt5 / websockets / pyinstaller
   - 安装 NSIS（通过 choco）
   - 用 PyInstaller 打包客户端和服务器
   - 用 NSIS 编译安装器
4. 最终产物：`ConnectHub-Setup.exe`

---

## ❓ 常见问题

**Q: 双击安装包没反应？**
A: 请确认 Windows 允许运行外部应用，右键 → 属性 → 解除锁定。

**Q: 提示无法连接服务器？**
A: 检查 ConnectHub 服务器.exe 是否在运行，服务器地址是否正确，防火墙是否放行 8765 端口。

**Q: 如何卸载？**
A: 打开"设置 → 应用 → ConnectHub → 卸载"，或运行安装目录下的 `Uninstall.exe`。

**Q: Release 页面没有下载文件？**
A: Release 页面的安装包由 GitHub Actions 自动构建，一般 5-10 分钟后出现。如果构建失败，可以本地运行 `build-installer.bat` 自行构建。

---

## 🛡 安全提示

ConnectHub 为小团队协作设计。部署在公网时请设置复杂密码并限制端口访问。
