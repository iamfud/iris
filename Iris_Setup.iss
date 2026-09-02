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
CloseApplications=no
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
; Run-at-startup is written conditionally in [Code] CurStepChanged (HKLM to survive
; admin elevation, applying to the signed-in user). Removed here to avoid an
; unconditional empty write that conflicts with the checkbox logic.

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Iris"
Type: filesandordirs; Name: "{localappdata}\Iris"

[Run]
Filename: "{app}\Iris.exe"; Description: "Launch Iris now"; Flags: nowait postinstall skipifsilent; Check: NotVCInstallFailed

[Code]
var
  NeedsReboot: Boolean;
  VCInstallFailed: Boolean;
  VCProgress: TOutputProgressWizardPage;

function NotVCInstallFailed: Boolean;
begin
  Result := not VCInstallFailed;
end;

type
  TProcessInformation = record
    hProcess: THandle;
    hThread: THandle;
    dwProcessId: DWord;
    dwThreadId: DWord;
  end;

const
  CREATE_NO_WINDOW = $08000000;
  WAIT_OBJECT_0 = $00000000;
  WAIT_TIMEOUT = $00000102;
  WAIT_FAILED = $FFFFFFFF;

function CreateProcessA(lpApplicationName: AnsiString; lpCommandLine: AnsiString;
  lpProcessAttributes: Integer; lpThreadAttributes: Integer; bInheritHandles: Boolean;
  dwCreationFlags: DWord; lpEnvironment: Integer; lpCurrentDirectory: AnsiString;
  lpStartupInfo: Integer; var lpProcessInformation: TProcessInformation): Boolean;
  external 'CreateProcessA@kernel32.dll stdcall';

function WaitForSingleObject(hHandle: THandle; dwMilliseconds: DWord): DWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';

procedure CloseHandle(hObject: THandle);
  external 'CloseHandle@kernel32.dll stdcall';

function GetExitCodeProcess(hProcess: THandle; var lpExitCode: DWord): Boolean;
  external 'GetExitCodeProcess@kernel32.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Instantly terminate any running Iris app and child processes (<50ms) }
  Exec('taskkill.exe', '/IM Iris.exe /F /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

function IsWebView2Installed: Boolean;
var
  Version: String;
begin
  // Check Microsoft WebView2 Client GUID {F3017226-FE2A-4295-8BDF-00C324E0F2B7} across 64-bit, 32-bit, and HKCU
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C324E0F2B7}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C324E0F2B7}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C324E0F2B7}', 'pv', Version);
end;

function IsVCRedistInstalled: Boolean;
var
  Installed: Cardinal;
begin
  Result :=
    (RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and (Installed = 1)) or
    (RegQueryDWordValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and (Installed = 1));
end;

function ExecuteAndWait(const Filename, Params: String; var ExitCode: DWord): Boolean;
var
  PI: TProcessInformation;
  i: Integer;
begin
  Result := False;
  if not CreateProcessA(Filename, '"' + Filename + '" ' + Params,
      0, 0, False, CREATE_NO_WINDOW, 0, '', 0, PI) then
    Exit;
  try
    while (WaitForSingleObject(PI.hProcess, 200) = WAIT_TIMEOUT) do
    begin
      { Indeterminate-looking progress that also pumps the message queue,
        keeping the wizard window responsive and movable during the install. }
      i := (i + 5) mod 100;
      VCProgress.SetProgress(i, 100);
      WizardForm.Refresh;
      Sleep(10);
    end;
    Result := GetExitCodeProcess(PI.hProcess, ExitCode);
  finally
    CloseHandle(PI.hThread);
    CloseHandle(PI.hProcess);
  end;
end;

procedure InstallVCRedist;
var
  exe: String;
  ResultCode: DWord;
begin
  if IsVCRedistInstalled then
    Exit;

  VCProgress := CreateOutputProgressPage(
    'Installing Microsoft Visual C++ Runtime',
    'This may take a minute. Iris will launch automatically when it is finished.');
  VCProgress.Show;
  try
    exe := ExpandConstant('{tmp}\iris_deps\vc_redist.x64.exe');
    if ExecuteAndWait(exe, '/install /quiet /norestart', ResultCode) then
    begin
      if ResultCode = 0 then
      begin
        { Success }
      end
      else if ResultCode = 3010 then
      begin
        NeedsReboot := True;
      end
      else
      begin
        VCInstallFailed := True;
        MsgBox('The Microsoft Visual C++ Runtime could not be installed (error ' +
          IntToStr(ResultCode) + ').' + #13#10 +
          'Iris may not run correctly.', mbError, MB_OK);
      end;
    end
    else
    begin
      VCInstallFailed := True;
      MsgBox('Failed to start the Microsoft Visual C++ Runtime installer.' + #13#10 +
        'Iris may not run correctly.', mbError, MB_OK);
    end;
  finally
    VCProgress.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Configuring dependencies...';
    WizardForm.Update;

    { Install the Microsoft Visual C++ Runtime first (skipped if already present) }
    InstallVCRedist;

    { Install WebView2 Runtime via Evergreen Bootstrapper only if not already present }
    if not IsWebView2Installed then
    begin
      WizardForm.StatusLabel.Caption := 'Installing Dependencies...';
      WizardForm.Update;
      Exec(ExpandConstant('{tmp}\iris_deps\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    { Install Interception driver — reboot required if success }
    WizardForm.StatusLabel.Caption := 'Configuring input driver...';
    WizardForm.Update;
    Exec(ExpandConstant('{tmp}\iris_deps\install-interception.exe'), '/install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode = 3010 then
      NeedsReboot := True;

    { Run Iris at startup if the task was selected. Written to HKLM (CurrentVersion\Run)
      instead of HKCU: the installer runs elevated (PrivilegesRequired=admin), so an HKCU
      write lands in the ELEVATED admin account's hive, not the signed-in user's hive that
      Windows reads for per-user autostart. HKLM is machine-wide and applies to the real user. }
    if WizardIsTaskSelected('startup') then
      RegWriteStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Iris',
        '"' + ExpandConstant('{app}\Iris.exe') + '"')
    else
      RegDeleteValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Iris');
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
