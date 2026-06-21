[Setup]
AppName=ConnectHub
AppVersion=1.1.0
DefaultDirName={pf}\ConnectHub
DefaultGroupName=ConnectHub
OutputBaseFilename=ConnectHub-Setup
OutputDir=..
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\ConnectHub-Client.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\ConnectHub-Client.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ConnectHub-Server.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ConnectHub 客户端"; Filename: "{app}\ConnectHub-Client.exe"
Name: "{group}\ConnectHub 服务端"; Filename: "{app}\ConnectHub-Server.exe"
Name: "{group}\卸载 ConnectHub"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ConnectHub 客户端"; Filename: "{app}\ConnectHub-Client.exe"
Name: "{userdesktop}\ConnectHub 服务端"; Filename: "{app}\ConnectHub-Server.exe"
