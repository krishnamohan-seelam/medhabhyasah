[Setup]
; AppId must never change: it lets a new installer upgrade an existing install in place.
AppId={{6C1B7E52-3D7A-4F0B-9B5E-8A2F4D1C9E70}
AppName=Medhabhyasah
AppVersion=0.1.0
AppPublisher=Krishna Mohan Seelam
DefaultDirName={localappdata}\Medhabhyasah
DefaultGroupName=Medhabhyasah
OutputBaseFilename=Medhabhyasah-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayName=Medhabhyasah
UninstallDisplayIcon={app}\Medhabhyasah.exe
CloseApplications=yes
OutputDir=..\installer_output

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\Medhabhyasah\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Medhabhyasah"; Filename: "{app}\Medhabhyasah.exe"
Name: "{group}\Uninstall Medhabhyasah"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Medhabhyasah"; Filename: "{app}\Medhabhyasah.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Medhabhyasah.exe"; Description: "Launch Medhabhyasah"; Flags: nowait postinstall skipifsilent

[Code]
{ The app window is Microsoft Edge WebView2. It ships with Windows 11 and current
  Windows 10, but older Windows 10 machines may lack it. }
const
  WebView2Guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Installed(): Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2Guid, 'pv', Version) or
     RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2Guid, 'pv', Version) or
     RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2Guid, 'pv', Version))
    and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
  if not WebView2Installed() then
  begin
    if MsgBox('Medhabhyasah needs the Microsoft Edge WebView2 Runtime, which was not found on this computer.' + #13#10#13#10 +
              'Click Yes to open the Microsoft download page (install it, then run this setup again), or No to continue anyway.',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
      Result := False;
    end;
  end;
end;
