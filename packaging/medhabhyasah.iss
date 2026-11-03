[Setup]
AppName=Medhabhyasah
AppVersion=0.1.0
AppPublisher=Krishna Mohan Seelam
DefaultDirName={localappdata}\Medhabhyasah
DefaultGroupName=Medhabhyasah
OutputBaseFilename=Medhabhyasah-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
OutputDir=..\installer_output

[Files]
Source: "..\dist\Medhabhyasah\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Medhabhyasah"; Filename: "{app}\Medhabhyasah.exe"
Name: "{group}\Uninstall Medhabhyasah"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Medhabhyasah.exe"; Description: "Launch Medhabhyasah"; Flags: nowait postinstall skipifsilent
