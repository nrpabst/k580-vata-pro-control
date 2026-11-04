; Installer for K580 Control (Inno Setup 6). Built by tools\build_exe.py, which passes the version,
; after it has made dist\K580 Control.exe. Installs per user (no admin), adds Start menu (and optionally
; desktop) shortcuts, can start the app with Windows, and shows up in Apps with an Uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B21AD262-5683-4099-8F92-C7F3734AB586}
AppName=K580 Control
AppVersion={#AppVersion}
AppVerName=K580 Control {#AppVersion}
AppPublisher=K580 Control (unofficial, open source)
AppPublisherURL=https://github.com/nrpabst/k580-vata-pro-control
AppSupportURL=https://github.com/nrpabst/k580-vata-pro-control/issues
DefaultDirName={localappdata}\Programs\K580 Control
DefaultGroupName=K580 Control
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=K580-Control-Setup-{#AppVersion}
SetupIconFile=..\build\k580-control.ico
UninstallDisplayIcon={app}\K580 Control.exe
UninstallDisplayName=K580 Control
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start K580 Control when Windows starts (in the system tray)"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\K580 Control.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\K580 Control"; Filename: "{app}\K580 Control.exe"
Name: "{userdesktop}\K580 Control"; Filename: "{app}\K580 Control.exe"; Tasks: desktopicon

[Registry]
; the same entry the app's own "Start with Windows" setting writes, so that checkbox shows it as on
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "K580 Control"; ValueData: """{app}\K580 Control.exe"" --tray"; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\K580 Control.exe"; Description: "Open K580 Control now"; Flags: nowait postinstall skipifsilent
; an automatic update (the app runs this installer silently with /update=1): start the new version
Filename: "{app}\K580 Control.exe"; Flags: nowait; Check: IsAutoUpdate

[UninstallRun]
; the app keeps running in the tray; close it so its file can be removed
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im ""K580 Control.exe"""; Flags: runhidden; RunOnceId: "CloseApp"

[Code]
function IsAutoUpdate: Boolean;
begin
  Result := ExpandConstant('{param:update|0}') = '1';
end;

// The app keeps running in the tray, and closing the window only hides it, so Windows' "close
// applications" step can't close it. Before copying files, give a running copy a moment to quit by
// itself (an automatic update tells it to), then end any copy that's still there. The packaged app is
// two processes (a launcher and the app); the launcher can outlive the app, so repeat until none are left.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code, Tries: Integer;
begin
  if IsAutoUpdate then
    Sleep(3000);
  for Tries := 1 to 4 do
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /t /im "K580 Control.exe"', '', SW_HIDE,
         ewWaitUntilTerminated, Code);
    Log(Format('taskkill attempt %d: exit code %d', [Tries, Code]));   // 128 = none left
    if Code = 128 then
      Break;
    Sleep(700);
  end;
  Result := '';
end;

// the app's own Start with Windows setting may have added the startup entry even if the installer's
// task was off: remove it on uninstall either way
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'K580 Control');
end;
