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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\ConnectHub-Client\*"; DestDir: "{app}\client"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "dist\ConnectHub-Server\*"; DestDir: "{app}\server"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\ConnectHub"; Filename: "{app}\client\ConnectHub-Client.exe"
Name: "{group}\ConnectHub Server"; Filename: "{app}\server\ConnectHub-Server.exe"
Name: "{group}\Uninstall ConnectHub"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ConnectHub"; Filename: "{app}\client\ConnectHub-Client.exe"
Name: "{userdesktop}\ConnectHub Server"; Filename: "{app}\server\ConnectHub-Server.exe"

[Run]
Filename: "{app}\client\ConnectHub-Client.exe"; Description: "Launch ConnectHub"; Flags: nowait postinstall skipifsilent
