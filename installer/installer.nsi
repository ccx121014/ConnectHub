; ============================================================
; ConnectHub 安装器 (NSIS)
; 编译方式: makensis installer.nsi
; 产物: ConnectHub-Setup.exe
; ============================================================

; 要求 NSIS 3.x
!pragma warning disable 2009 3004 3005

; 安装器基本信息
OutFile "ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
Name "ConnectHub"
Caption "ConnectHub 安装向导"
BrandingText "ConnectHub"
CRCCheck on
VIAddVersionKey "ProductName" "ConnectHub"
VIAddVersionKey "ProductVersion" "1.0.5"
VIAddVersionKey "CompanyName" "ConnectHub"
VIAddVersionKey "FileDescription" "ConnectHub 安装程序"
VIAddVersionKey "LegalTrademarks" "ConnectHub"
VIProductVersion "1.0.5.0"
VIFileVersion "1.0.5.0"

; 界面设置
!include "MUI2.nsh"

; 现代界面
!define MUI_ICON "installer\icon.ico"
!define MUI_HEADERIMAGE
!define MUI_ABORTWARNING
!define MUI_LICENSEPAGE_RADIOBUTTONS
!define MUI_FINISHPAGE_RUN "$INSTDIR\ConnectHub-Client.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 ConnectHub 客户端"
!define MUI_FINISHPAGE_NOAUTOCLOSE

; 页面顺序
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "installer\license.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; 语言
!insertmacro MUI_LANGUAGE "SimpChinese"

; ============================================================
; 默认安装段
; ============================================================

Section "" SecHidden
  SectionIn RO

  SetOutPath "$INSTDIR"

  ; 写入安装目录到注册表
  WriteRegStr HKLM "Software\ConnectHub" "" $INSTDIR
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayName" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayVersion" "1.0.5"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "Publisher" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoRepair" 1
SectionEnd

; ============================================================
; 客户端组件
; ============================================================

Section "客户端 (ConnectHub-Client)" SecClient
  SectionIn 1
  AddSize 80000

  SetOutPath "$INSTDIR\client"

  ; 拷贝客户端所有文件
  File /r "dist\ConnectHub-Client\*.*"

  ; 生成启动脚本
  SetOutPath "$INSTDIR"
  FileOpen $0 "$INSTDIR\启动客户端.bat" w
  FileWrite $0 '@echo off$\r$\n'
  FileWrite $0 'chcp 65001 >nul$\r$\n'
  FileWrite $0 'cd /d "%~dp0client"$\r$\n'
  FileWrite $0 'start "" "ConnectHub-Client.exe"$\r$\n'
  FileClose $0

  ; 创建桌面快捷方式
  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$SMPROGRAMS\ConnectHub\客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe" "" "$INSTDIR\client\ConnectHub-Client.exe" 0
  CreateShortCut "$DESKTOP\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe" "" "$INSTDIR\client\ConnectHub-Client.exe" 0

SectionEnd

; ============================================================
; 服务器组件
; ============================================================

Section "服务器 (ConnectHub-Server)" SecServer
  SectionIn 1
  AddSize 10000

  SetOutPath "$INSTDIR\server"
  File /r "dist\ConnectHub-Server\*.*"

  ; 生成启动脚本
  SetOutPath "$INSTDIR"
  FileOpen $0 "$INSTDIR\启动服务器.bat" w
  FileWrite $0 '@echo off$\r$\n'
  FileWrite $0 'chcp 65001 >nul$\r$\n'
  FileWrite $0 'cd /d "%~dp0server"$\r$\n'
  FileWrite $0 'start "" "ConnectHub-Server.exe"$\r$\n'
  FileClose $0

  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$SMPROGRAMS\ConnectHub\服务器.lnk" "$INSTDIR\server\ConnectHub-Server.exe" "" "$INSTDIR\server\ConnectHub-Server.exe" 0
  CreateShortCut "$DESKTOP\ConnectHub 服务器.lnk" "$INSTDIR\server\ConnectHub-Server.exe" "" "$INSTDIR\server\ConnectHub-Server.exe" 0

SectionEnd

; ============================================================
; 卸载程序
; ============================================================

Section "卸载"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$SMPROGRAMS\ConnectHub\卸载.lnk" "$INSTDIR\Uninstall.exe"

  ; 版本说明文件
  FileOpen $0 "$INSTDIR\版本说明.txt" w
  FileWrite $0 'ConnectHub v1.0.5$\r$\n$\r$\n'
  FileWrite $0 '使用方法:$\r$\n'
  FileWrite $0 '  1. 双击桌面上的 "ConnectHub 服务器.lnk" 启动服务器$\r$\n'
  FileWrite $0 '  2. 双击桌面上的 "ConnectHub 客户端.lnk" 启动客户端$\r$\n'
  FileWrite $0 '  3. 登录时: 服务器地址=服务器IP, 端口=8765, 用户名=自取$\r$\n$\r$\n'
  FileWrite $0 '卸载: 运行 Uninstall.exe$\r$\n'
  FileClose $0

  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "EstimatedSize" 90000
SectionEnd

; ============================================================
; 卸载脚本
; ============================================================

Section "Uninstall"
  ; 删除桌面快捷方式
  Delete "$DESKTOP\ConnectHub 客户端.lnk"
  Delete "$DESKTOP\ConnectHub 服务器.lnk"

  ; 删除开始菜单
  RMDir /r "$SMPROGRAMS\ConnectHub"

  ; 删除程序文件
  RMDir /r "$INSTDIR\client"
  RMDir /r "$INSTDIR\server"
  Delete "$INSTDIR\启动客户端.bat"
  Delete "$INSTDIR\启动服务器.bat"
  Delete "$INSTDIR\版本说明.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ; 删除注册表项
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub"
  DeleteRegKey HKLM "Software\ConnectHub"
SectionEnd

; ============================================================
; 段描述
; ============================================================

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecClient} "ConnectHub 客户端（聊天、文件传输、远程桌面）"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecServer} "ConnectHub 服务器（必须在一台电脑上运行）"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ============================================================
; 函数 - 检测旧版本并卸载
; ============================================================

Function .onInit
  ; 检测是否有旧版本
  ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString"
  StrCmp $R0 "" done_no_uninstall
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "检测到旧版本的 ConnectHub。$\r$\n是否先卸载旧版本再继续？" IDOK uninstall_old
    Abort
  uninstall_old:
    ExecWait '$R0 _?=$INSTDIR'
  done_no_uninstall:
FunctionEnd

Function un.onUninstSuccess
  HideWindow
  MessageBox MB_OK|MB_ICONINFORMATION "ConnectHub 已成功卸载。"
FunctionEnd
