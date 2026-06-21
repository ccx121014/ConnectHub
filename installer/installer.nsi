; ============================================================
; ConnectHub 安装器 (NSIS) - 简化版，无需图标文件
; 编译方式: makensis installer\installer.nsi
; ============================================================

Name "ConnectHub"
Caption "ConnectHub 安装向导"
BrandingText "ConnectHub"
OutFile "ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show
CRCCheck on

; 版本信息
VIAddVersionKey "ProductName" "ConnectHub"
VIAddVersionKey "ProductVersion" "1.0.6"
VIAddVersionKey "CompanyName" "ConnectHub"
VIAddVersionKey "FileDescription" "ConnectHub 安装程序"
VIAddVersionKey "LegalCopyright" "ConnectHub"
VIProductVersion "1.0.6.0"
VIFileVersion "1.0.6.0"

; 界面设置 - 使用内置现代界面
!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\client\ConnectHub-Client.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 ConnectHub 客户端"
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_ABORTWARNING_TEXT "确定要退出安装吗？"

; 页面
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; 语言 - 使用内置简体中文
!insertmacro MUI_LANGUAGE "SimpChinese"

; Section: 客户端组件
Section "客户端 (必选)" SecClient
  SectionIn RO
  SetOutPath "$INSTDIR\client"
  File /r "dist\ConnectHub-Client\*.*"

  ; 创建开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$SMPROGRAMS\ConnectHub\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe" "" "" 0
  CreateShortCut "$DESKTOP\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe" "" "" 0

  ; 写入注册表
  WriteRegStr HKLM "Software\ConnectHub" "" $INSTDIR
  WriteRegStr HKLM "Software\ConnectHub" "Version" "1.0.6"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayName" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayVersion" "1.0.6"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "Publisher" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoRepair" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "EstimatedSize" 90000

  ; 创建使用说明
  SetOutPath "$INSTDIR"
  FileOpen $0 "$INSTDIR\使用说明.txt" w
  FileWrite $0 'ConnectHub v1.0.6\r\n\r\n'
  FileWrite $0 '使用方法:\r\n'
  FileWrite $0 ' 1. 先双击桌面 "ConnectHub 服务器.lnk" 启动服务器（只需要在一台电脑上）\r\n'
  FileWrite $0 ' 2. 再双击桌面 "ConnectHub 客户端.lnk" 启动客户端（每位用户）\r\n'
  FileWrite $0 ' 3. 登录时填写: 服务器=服务器电脑IP, 端口=8765, 用户名=自取\r\n\r\n'
  FileWrite $0 '功能: 即时聊天 / 文件传输 / 远程桌面\r\n'
  FileWrite $0 '卸载: 控制面板 - 应用与功能 - ConnectHub - 卸载\r\n'
  FileClose $0
SectionEnd

; Section: 服务器组件
Section "服务器" SecServer
  SectionIn 1
  SetOutPath "$INSTDIR\server"
  File /r "dist\ConnectHub-Server\*.*"

  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$SMPROGRAMS\ConnectHub\ConnectHub 服务器.lnk" "$INSTDIR\server\ConnectHub-Server.exe" "" "" 0
  CreateShortCut "$DESKTOP\ConnectHub 服务器.lnk" "$INSTDIR\server\ConnectHub-Server.exe" "" "" 0
SectionEnd

; Section: 卸载程序
Section "卸载程序"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\卸载 ConnectHub.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

; 卸载脚本
Section "Uninstall"
  ; 桌面快捷方式
  Delete "$DESKTOP\ConnectHub 客户端.lnk"
  Delete "$DESKTOP\ConnectHub 服务器.lnk"

  ; 开始菜单
  RMDir /r "$SMPROGRAMS\ConnectHub"

  ; 程序文件
  RMDir /r "$INSTDIR\client"
  RMDir /r "$INSTDIR\server"
  Delete "$INSTDIR\使用说明.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ; 注册表
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub"
  DeleteRegKey HKLM "Software\ConnectHub"
SectionEnd

; 段描述
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecClient} "ConnectHub 客户端（用于连接服务器进行聊天、文件传输、远程桌面）"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecServer} "ConnectHub 服务器（用于其他客户端连接，只需要一台电脑运行）"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; 安装完成提示
Function .onInstSuccess
  MessageBox MB_OK "ConnectHub 已成功安装。$\r$\n$\r$\n使用说明：$\r\n  1. 先双击桌面 "ConnectHub 服务器" 启动服务器（只需要一台电脑）$\r\n  2. 再双击桌面 "ConnectHub 客户端" 启动客户端$\r\n  3. 登录时填写: 服务器地址=服务器IP, 端口=8765, 用户名=自取"
FunctionEnd

; 卸载完成提示
Function un.onUninstSuccess
  HideWindow
  MessageBox MB_OK|MB_ICONINFORMATION "ConnectHub 已成功卸载。"
FunctionEnd
