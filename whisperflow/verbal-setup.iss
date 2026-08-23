; Inno Setup Script for Verbal Windows Installer
; Builds a silent-install capable .exe that auto-updates the app

#define MyAppName "Verbal"
; MyAppVersion is passed in from CI via `ISCC.exe /DMyAppVersion=X.Y.Z` (kept
; in sync with config.APP_VERSION, same source of truth the release pipeline
; already enforces — see build-release.yml's "Tag must match config.APP_VERSION"
; check). #ifndef guards the local/manual-build case where no /D is passed.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppPublisher "Verbal"
#define MyAppExeName "Verbal.exe"

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
DefaultDirName={autopf}\Verbal
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=VerbalSetup
SetupIconFile=assets\icon.ico
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
Source: "dist\Verbal.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\sounds\*"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Install the Edge WebView2 Evergreen runtime if it's absent. pywebview's
; edgechromium backend requires it. The bootstrapper is downloaded during the
; wizard (see [Code] below) to {tmp}. Runs silently and waits for completion so
; the runtime exists before Verbal first launches.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Edge WebView2 runtime..."; Flags: waituntilterminated; Check: WebView2Missing
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

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
    may be absent — Verbal falls back to whatever runtime is available. }
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
