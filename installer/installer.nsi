Name "ConnectHub"
OutFile "..\ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

Section "ConnectHub" SecMain
  SetOutPath "$INSTDIR\client"
  File /r "..\dist\ConnectHub-Client\*"

  SetOutPath "$INSTDIR\server"
  File /r "..\dist\ConnectHub-Server\*"

  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$DESKTOP\ConnectHub 客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe"
  CreateShortCut "$DESKTOP\ConnectHub 服务端.lnk" "$INSTDIR\server\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\客户端.lnk" "$INSTDIR\client\ConnectHub-Client.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\服务端.lnk" "$INSTDIR\server\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\卸载.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "Software\ConnectHub" "" $INSTDIR
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayName" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayVersion" "1.0.9"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "Publisher" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoRepair" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "EstimatedSize" 50000

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
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
