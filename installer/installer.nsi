; ============================================================
; ConnectHub 安装器 (NSIS)
; 编译方式: makensis installer\installer.nsi
; 输出: ConnectHub-Setup.exe
; ============================================================

Name "ConnectHub"
OutFile "ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

; ============================================================
; 安装主流程
; ============================================================

Section "ConnectHub"
  SectionIn RO

  ; --- 安装客户端文件 ---
  SetOutPath "$INSTDIR\client"
  File /r "dist\ConnectHub-Client\*.*"

  ; --- 安装服务器文件 ---
  SetOutPath "$INSTDIR\server"
  File /r "dist\ConnectHub-Server\*.*"

  ; --- 创建桌面快捷方式 ---
  CreateShortCut "$DESKTOP\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe"
  CreateShortCut "$DESKTOP\ConnectHub 服务器.lnk" "$INSTDIR\server\ConnectHub-Server.exe"

  ; --- 创建开始菜单 ---
  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$SMPROGRAMS\ConnectHub\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\ConnectHub 服务器.lnk" "$INSTDIR\server\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; --- 写入注册表 ---
  WriteRegStr HKLM "Software\ConnectHub" "" $INSTDIR
  WriteRegStr HKLM "Software\ConnectHub" "Version" "1.0.6"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayName" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayVersion" "1.0.6"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "Publisher" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "QuietUninstallString" "$INSTDIR\Uninstall.exe /S"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoRepair" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "EstimatedSize" 90000

  ; --- 创建卸载程序 ---
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

; ============================================================
; 卸载脚本
; ============================================================

Section "Uninstall"
  Delete "$DESKTOP\ConnectHub 客户端.lnk"
  Delete "$DESKTOP\ConnectHub 服务器.lnk"
  RMDir /r "$SMPROGRAMS\ConnectHub"
  RMDir /r "$INSTDIR\client"
  RMDir /r "$INSTDIR\server"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub"
  DeleteRegKey HKLM "Software\ConnectHub"
SectionEnd
