Unicode True
Name "ConnectHub"
OutFile "..\ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

!define APP_VERSION "1.4.23"

# ---------------------------------------------------------------------------
# 自定义宏：静默杀死正在运行的 ConnectHub 进程
# ---------------------------------------------------------------------------
!macro KillRunningProcesses
  nsExec::Exec 'taskkill /F /IM "ConnectHub-Client.exe" /T'
  nsExec::Exec 'taskkill /F /IM "ConnectHub-Server.exe" /T'
  Sleep 1500
!macroend

# ---------------------------------------------------------------------------
# 预安装检查（静默关闭进程，不弹窗）
# ---------------------------------------------------------------------------
Function .onInit
  !insertmacro KillRunningProcesses
FunctionEnd

# ---------------------------------------------------------------------------
# 预卸载检查（静默关闭进程，不弹窗）
# ---------------------------------------------------------------------------
Function un.onInit
  !insertmacro KillRunningProcesses
FunctionEnd

# ---------------------------------------------------------------------------
# 主安装段
# ---------------------------------------------------------------------------
Section "ConnectHub" SecMain
  !insertmacro KillRunningProcesses

  SetOutPath "$INSTDIR\client"
  SetOverwrite on
  File /r "..\dist\ConnectHub-Client\*"

  SetOutPath "$INSTDIR\server"
  SetOverwrite on
  File /r "..\dist\ConnectHub-Server\*"

  Sleep 500

  # 桌面快捷方式（中文名称）
  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$DESKTOP\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe"
  CreateShortCut "$DESKTOP\ConnectHub 服务端.lnk" "$INSTDIR\server\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\服务端.lnk" "$INSTDIR\server\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\卸载.lnk" "$INSTDIR\Uninstall.exe"

  # 写入注册表
  WriteRegStr HKLM "Software\ConnectHub" "" $INSTDIR
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayName" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "Publisher" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoRepair" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "EstimatedSize" 50000

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

# ---------------------------------------------------------------------------
# 卸载段
# ---------------------------------------------------------------------------
Section "Uninstall"
  !insertmacro KillRunningProcesses

  Delete "$DESKTOP\ConnectHub 客户端.lnk"
  Delete "$DESKTOP\ConnectHub 服务端.lnk"
  RMDir /r "$SMPROGRAMS\ConnectHub"

  RMDir /r "$INSTDIR\client"
  RMDir /r "$INSTDIR\server"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub"
  DeleteRegKey HKLM "Software\ConnectHub"
SectionEnd
