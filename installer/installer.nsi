Unicode True
Name "ConnectHub"
OutFile "..\ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

!define APP_VERSION "1.4.20"

# ---------------------------------------------------------------------------
# 自定义函数：杀死正在运行的 ConnectHub 进程
# ---------------------------------------------------------------------------
!macro KillRunningProcesses
  # 尝试通过 taskkill 关闭正在运行的客户端和服务端
  nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Client.exe" /T'
  nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Server.exe" /T'
  # 等待进程完全退出（避免文件仍被占用）
  Sleep 1500
!macroend

# ---------------------------------------------------------------------------
# 自定义函数：带重试的文件复制
# ---------------------------------------------------------------------------
Function CopyWithRetry
  Pop $0  # 源文件路径
  Pop $1  # 目标文件路径
  Pop $2  # 标志：是否关键文件

  StrCpy $3 0  # 重试计数
  StrCpy $4 0  # 失败标志

  ${Do}
    ClearErrors
    CopyFiles /SILENT /FILESONLY $0 $1
    ${If} ${Errors}
      IntOp $3 $3 + 1
      ${If} $3 >= 3
        StrCpy $4 1
        ${ExitDo}
      ${EndIf}
      # 重试前先尝试关闭可能占用文件的进程
      nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Client.exe" /T'
      nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Server.exe" /T'
      Sleep 1000
    ${Else}
      ${ExitDo}
    ${EndIf}
  ${Loop}

  ${If} $4 == 1
    ${If} $2 == 1
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

# ---------------------------------------------------------------------------
# 预安装检查
# ---------------------------------------------------------------------------
Function .onInit
  # 如果检测到已有安装，提示用户
  ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString"
  ${If} $0 != ""
    MessageBox MB_OK|MB_ICONINFORMATION "检测到已安装的 ConnectHub，将先关闭运行中的进程并更新。$\r$\nInstall will close running ConnectHub processes first." /SD IDOK
  ${EndIf}

  # 关闭可能正在运行的进程
  nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Client.exe" /T'
  nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Server.exe" /T'
  Sleep 1500
FunctionEnd

# ---------------------------------------------------------------------------
# 预卸载检查
# ---------------------------------------------------------------------------
Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO "确定要卸载 ConnectHub？" /SD IDYES IDYES +2
    Abort
  # 关闭进程
  nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Client.exe" /T'
  nsExec::ExecToLog 'taskkill /F /IM "ConnectHub-Server.exe" /T'
  Sleep 1000
FunctionEnd

# ---------------------------------------------------------------------------
# 主安装段
# ---------------------------------------------------------------------------
Section "ConnectHub" SecMain
  # 再次确保进程已关闭
  !insertmacro KillRunningProcesses

  # 设置输出目录
  SetOutPath "$INSTDIR\client"
  # 使用 setoverwrite 强制覆盖已存在的文件
  SetOverwrite on
  # 添加 on/off 标志：on = 总是覆盖，try = 仅当存在时覆盖，off = 不覆盖
  File /r "..\dist\ConnectHub-Client\*"

  SetOutPath "$INSTDIR\server"
  SetOverwrite on
  File /r "..\dist\ConnectHub-Server\*"

  # 等待文件系统稳定
  Sleep 500

  # 创建开始菜单快捷方式
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

  # 写入卸载程序
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

# ---------------------------------------------------------------------------
# 卸载段
# ---------------------------------------------------------------------------
Section "Uninstall"
  # 确保进程已关闭
  !insertmacro KillRunningProcesses

  # 删除快捷方式
  Delete "$DESKTOP\ConnectHub 客户端.lnk"
  Delete "$DESKTOP\ConnectHub 服务端.lnk"
  RMDir /r "$SMPROGRAMS\ConnectHub"

  # 删除安装文件
  RMDir /r "$INSTDIR\client"
  RMDir /r "$INSTDIR\server"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  # 删除注册表
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub"
  DeleteRegKey HKLM "Software\ConnectHub"
SectionEnd
