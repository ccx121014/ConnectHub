Name "ConnectHub"
OutFile "ConnectHub-Setup.exe"
InstallDir "$PROGRAMFILES\ConnectHub"
InstallDirRegKey HKLM "Software\ConnectHub" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

Section "ConnectHub" SecMain
  SetOutPath "$INSTDIR"
  File "..\dist\ConnectHub-Client.exe"
  File "..\dist\ConnectHub-Server.exe"

  CreateDirectory "$SMPROGRAMS\ConnectHub"
  CreateShortCut "$DESKTOP\ConnectHub 客户端.lnk" "$INSTDIR\ConnectHub-Client.exe"
  CreateShortCut "$DESKTOP\ConnectHub 服务端.lnk" "$INSTDIR\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\客户端.lnk" "$INSTDIR\ConnectHub-Client.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\服务端.lnk" "$INSTDIR\ConnectHub-Server.exe"
  CreateShortCut "$SMPROGRAMS\ConnectHub\卸载.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "Software\ConnectHub" "" $INSTDIR
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayName" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "DisplayVersion" "1.0.7"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "Publisher" "ConnectHub"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "NoRepair" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub" "EstimatedSize" 60000

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\ConnectHub 客户端.lnk"
  Delete "$DESKTOP\ConnectHub 服务端.lnk"
  RMDir /r "$SMPROGRAMS\ConnectHub"
  Delete "$INSTDIR\ConnectHub-Client.exe"
  Delete "$INSTDIR\ConnectHub-Server.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConnectHub"
  DeleteRegKey HKLM "Software\ConnectHub"
SectionEnd
