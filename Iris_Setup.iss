[Setup]
AppId={{B3A7F6D2-4E8C-4F1A-9C5B-2D6E8F0A1B3C}
AppName=Iris
AppVersion=0.31
AppPublisher=Iris
DefaultDirName={autopf}\Iris
DefaultGroupName=Iris
OutputDir=Installer
OutputBaseFilename=Iris_Setup
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=media\Iris_setup.ico
UninstallDisplayIcon={app}\Iris.exe
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\Iris.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\plugins\*"; DestDir: "{userdocs}\Iris\plugins"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Installer\deps\vc_redist.x64.exe"; DestDir: "{tmp}\iris_deps"; Flags: deleteafterinstall
Source: "Installer\deps\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}\iris_deps"; Flags: deleteafterinstall
Source: "Installer\deps\Interception\Interception\command line installer\install-interception.exe"; DestDir: "{tmp}\iris_deps"; Flags: deleteafterinstall
Source: "Installer\deps\Interception\Interception\library\x64\interception.dll"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{userdocs}\Iris\plugins"
Name: "{userdocs}\Iris\Library\screenshots"
Name: "{userdocs}\Iris\Library\notes"

[Icons]
Name: "{group}\Iris"; Filename: "{app}\Iris.exe"
Name: "{group}\Uninstall Iris"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Iris"; Filename: "{app}\Iris.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Run Iris when you sign in to Windows"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Iris"; Flags: uninsdeletevalue

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Iris"
Type: filesandordirs; Name: "{localappdata}\Iris"

[Run]
Filename: "{tmp}\iris_deps\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Visual C++ Redistributable..."; Flags: waituntilterminated
Filename: "{app}\Iris.exe"; Description: "Launch Iris now"; Flags: nowait postinstall skipifsilent

[Code]
var
  NeedsReboot: Boolean;

function IsWebView2Installed: Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6279F0EA9}', 'pv', Version);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    { Install WebView2 Runtime via Evergreen Bootstrapper only if not already present }
    if not IsWebView2Installed then
      Exec(ExpandConstant('{tmp}\iris_deps\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    { Install Interception driver — reboot required if success }
    Exec(ExpandConstant('{tmp}\iris_deps\install-interception.exe'), '/install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode = 3010 then
      NeedsReboot := True;

    { Run Iris at startup if the task was selected }
    if WizardIsTaskSelected('startup') then
      RegWriteStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Iris',
        '"' + ExpandConstant('{app}\Iris.exe') + '"')
    else
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Iris');
  end;
end;

function NeedRestart: Boolean;
begin
  Result := NeedsReboot;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Terminate any running Iris processes (main app + panel child) for a clean uninstall }
    Exec('taskkill.exe', '/IM Iris.exe /F /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
