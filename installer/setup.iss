[Setup]
AppName=ConnectHub
AppVersion=1.0.9
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
UninstallDisplayIcon={app}\client\ConnectHub-Client.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; 从 onedir 文件夹递归复制客户端和服务端的所有文件
; 注：UPX 已预先压缩了所有 DLL
Source: "..\dist\ConnectHub-Client\*"; DestDir: "{app}\client"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\ConnectHub-Server\*"; DestDir: "{app}\server"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\ConnectHub 客户端"; Filename: "{app}\client\ConnectHub-Client.exe"
Name: "{group}\ConnectHub 服务端"; Filename: "{app}\server\ConnectHub-Server.exe"
Name: "{group}\卸载 ConnectHub"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ConnectHub 客户端"; Filename: "{app}\client\ConnectHub-Client.exe"
Name: "{userdesktop}\ConnectHub 服务端"; Filename: "{app}\server\ConnectHub-Server.exe"
