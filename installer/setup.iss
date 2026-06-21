[Setup]
AppName=ConnectHub
AppVersion=1.0.6
DefaultDirName={pf}\ConnectHub
DefaultGroupName=ConnectHub
OutputBaseFilename=ConnectHub-Setup
OutputDir=..
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\client\ConnectHub-Client.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\ConnectHub-Client\*"; DestDir: "{app}\client"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\ConnectHub-Server\*"; DestDir: "{app}\server"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\ConnectHub Client"; Filename: "{app}\client\ConnectHub-Client.exe"
Name: "{group}\ConnectHub Server"; Filename: "{app}\server\ConnectHub-Server.exe"
Name: "{group}\Uninstall ConnectHub"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ConnectHub Client"; Filename: "{app}\client\ConnectHub-Client.exe"
Name: "{userdesktop}\ConnectHub Server"; Filename: "{app}\server\ConnectHub-Server.exe"
