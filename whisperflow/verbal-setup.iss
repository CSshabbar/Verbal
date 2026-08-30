; Inno Setup Script for Flume Windows Installer
; Builds a silent-install capable .exe that auto-updates the app

#define MyAppName "Flume"
; MyAppVersion is passed in from CI via `ISCC.exe /DMyAppVersion=X.Y.Z` (kept
; in sync with config.APP_VERSION, same source of truth the release pipeline
; already enforces — see build-release.yml's "Tag must match config.APP_VERSION"
; check). #ifndef guards the local/manual-build case where no /D is passed.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppPublisher "Flume"
; Must match `name=` in the EXE(...) call of verbal-win.spec — that is what
; actually names the frozen PyInstaller output (dist\Flume\Flume.exe, onedir).
#define MyAppExeName "Flume.exe"

[Setup]
; This GUID is the installer's permanent identity — Windows uses it to
; recognize "this is an upgrade of the same app" across versions. It must
; NEVER change again once set. The previous value here was a placeholder
; that was never actually filled in with a real GUID (it contained the
; letters G-O, which aren't valid hex — Inno Setup would reject it outright).
; This is a genuinely random, freshly generated GUID (2026-08-23), not a
; template value, and must stay exactly this from now on.
AppId={{0F0305B3-E5F2-4102-9D1F-54542A135659}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Flume
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=FlumeSetup
SetupIconFile=assets\icon.ico
; Icon shown in Settings > Apps / "Programs and Features". Without this Windows
; falls back to a generic icon (or, via the shell icon cache, whatever it last
; saw for this AppId — the old Verbal art) after the Flume rebrand.
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller ONEDIR output (verbal-win.spec COLLECT, 2026-08-28): Flume.exe plus
; an _internal\ tree. Was `dist\Flume.exe` (one-file) — see the spec for why.
Source: "dist\Flume\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\sounds\*"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; IconFilename points at the standalone .ico (shipped via assets\*) rather than
; the exe's embedded resource. Windows' shell icon cache is keyed on the icon
; SOURCE path, and {app}\Flume.exe has been that source since the first install
; — so after the 2026-08-25 rebrand the Start menu / taskbar kept serving the
; cached old Verbal icon even though the new exe carried the new one. A new
; source path is a new cache key. CurStepChanged below also asks the shell to
; flush its icon cache after install.
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; Install the Edge WebView2 Evergreen runtime if it's absent. pywebview's
; edgechromium backend requires it. The bootstrapper is downloaded during the
; wizard (see [Code] below) to {tmp}. Runs silently and waits for completion so
; the runtime exists before Flume first launches.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Edge WebView2 runtime..."; Flags: waituntilterminated; Check: WebView2Missing
; No `skipifsilent` here (deliberately, as of the tray "update available"
; work): app/updater.py::install_update ALWAYS passes /SILENT to ISCC —
; even the "user clicked Yes in the update dialog" path, not just the
; auto_update-silent path — so `skipifsilent` was skipping this relaunch on
; EVERY app-triggered update install, silent or not, leaving the user to
; reopen Flume by hand every single time. Per Inno Setup's own semantics, a
; `postinstall`-flagged entry WITHOUT `skipifsilent` still runs automatically
; at the end of a /SILENT or /VERYSILENT install (there's no wizard "finish"
; checkbox to honor, so it just runs) — for a normal *interactive* manual
; install (someone double-clicking FlumeSetup.exe with no switches) this is
; unchanged: it still shows as the checked-by-default "Launch Flume" box on
; the wizard's final page.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Code]
// ---- Edge WebView2 Evergreen runtime bootstrap ----------------------------
// pywebview (edgechromium backend) needs the Edge WebView2 runtime. Detect it
// via the EdgeUpdate client GUID {F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}; if the
// 'pv' version value is missing/empty in every scope, download and run the
// Evergreen bootstrapper. Bootstrapper URL:
//   https://go.microsoft.com/fwlink/p/?LinkId=2124703
// The actual install happens via the [Run] entry above (Check: WebView2Missing);
// here we only make sure the bootstrapper file is present in {tmp}.
// (Note: {...} block comments do NOT nest in Pascal, so avoid literal braces
// inside them — that is why these are // line comments.)

var
  DownloadPage: TDownloadWizardPage;

const
  WV2_CLIENT = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WV2_CLIENT_WOW = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WV2_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';

function WebView2Installed(): Boolean;
var
  pv: String;
begin
  { Check per-machine (64-bit + 32-bit views) and per-user (installer runs at
    lowest privileges, so a per-user runtime is valid). }
  Result :=
    (RegQueryStringValue(HKLM, WV2_CLIENT_WOW, 'pv', pv) and (pv <> '') and (pv <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM, WV2_CLIENT, 'pv', pv) and (pv <> '') and (pv <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, WV2_CLIENT, 'pv', pv) and (pv <> '') and (pv <> '0.0.0.0'));
end;

function WebView2Missing(): Boolean;
begin
  Result := not WebView2Installed();
end;

// ---- Shell icon-cache refresh -----------------------------------------------
// SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0) tells Explorer that
// file associations / icons changed; it re-reads shortcut icons instead of
// serving the stale cached ones. Cheap and harmless when nothing changed.
procedure SHChangeNotify(wEventId: Integer; uFlags: Cardinal; dwItem1, dwItem2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

const
  SHCNE_ASSOCCHANGED = $08000000;
  SHCNF_IDLIST = $0000;

// ---- Make sure a running Flume is gone before files are replaced ------------
// CloseApplications=force relies on the Restart Manager, and RM can refuse:
// verified live 2026-08-28 (Win11 ARM64 VM) — "Can use RestartManager to avoid
// reboot? No (1: Permission Denied)" because a SYSTEM process (XtaCache) also
// mapped our files, so Flume.exe was never closed, DeleteFile failed with
// code 5 and the /SUPPRESSMSGBOXES install ABORTED and rolled back — i.e. an
// update that looked like it ran did nothing. The app's own updater os._exit()s
// before launching us, so this matters for a user double-clicking a new
// FlumeSetup.exe while Flume runs; make that path deterministic: taskkill
// (same user, no elevation needed) and wait until the process is gone.
function FlumeRunning(): Boolean;
var
  ResultCode: Integer;
begin
  { tasklist exits 0 either way; its output contains the image name only if found.
    FIND returns 1 when the string is absent. }
  Result := Exec(ExpandConstant('{cmd}'), '/C tasklist /FI "IMAGENAME eq Flume.exe" | find /I "Flume.exe" >nul',
                 '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode, Tries: Integer;
begin
  Result := '';
  if FlumeRunning() then begin
    Log('Flume.exe is running -- terminating it before install');
    { No /T: the app-launched installer is itself a child of Flume.exe (Popen,
      DETACHED_PROCESS does not reparent) — a tree kill could take out this
      very setup. WebView2 children die with their host anyway. }
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Flume.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Tries := 0;
    while FlumeRunning() and (Tries < 20) do begin
      Sleep(250);
      Tries := Tries + 1;
    end;
    if FlumeRunning() then
      Log('Flume.exe still running after taskkill; Restart Manager will have to handle it')
    else
      Log('Flume.exe terminated');
    { Give the OS a moment to release file handles / the tray icon. }
    Sleep(500);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    try
      SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0);
    except
      Log('SHChangeNotify failed: ' + GetExceptionMessage);
    end;
  end;
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  { On the Ready page, fetch the bootstrapper if the runtime isn't present.
    Failure to download is non-fatal: the [Run] Check still fires, but the file
    may be absent — Flume falls back to whatever runtime is available. }
  if (CurPageID = wpReady) and WebView2Missing() then begin
    DownloadPage.Clear;
    DownloadPage.Add(WV2_URL, 'MicrosoftEdgeWebview2Setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        Log('WebView2 bootstrapper download failed: ' + GetExceptionMessage);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
