[Setup]
AppName=ConnectHub
AppVersion=1.3.2
DefaultDirName={pf}\ConnectHub
DefaultGroupName=ConnectHub
OutputBaseFilename=ConnectHub-Setup
OutputDir=..
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\ConnectHub-Client\ConnectHub-Client.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\ConnectHub-Client\*"; DestDir: "{app}\ConnectHub-Client"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\ConnectHub-Server\*"; DestDir: "{app}\ConnectHub-Server"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ConnectHub 客户端"; Filename: "{app}\ConnectHub-Client\ConnectHub-Client.exe"
Name: "{group}\ConnectHub 服务端"; Filename: "{app}\ConnectHub-Server\ConnectHub-Server.exe"
Name: "{group}\卸载 ConnectHub"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ConnectHub 客户端"; Filename: "{app}\ConnectHub-Client\ConnectHub-Client.exe"
Name: "{userdesktop}\ConnectHub 服务端"; Filename: "{app}\ConnectHub-Server\ConnectHub-Server.exe"

[Run]
Filename: "{app}\ConnectHub-Client\ConnectHub-Client.exe"; Description: "启动 ConnectHub 客户端"; Flags: nowait postinstall skipifsilent
