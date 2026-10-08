#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputPath
  #error OutputPath is required
#endif
#ifndef BrowserDir
  #error BrowserDir is required
#endif

[Setup]
AppId={{B60FD775-5E70-4C13-91EC-CB07D8539FE0}
AppName=AIRate
AppVersion={#AppVersion}
AppPublisher=AIRate
AppPublisherURL=https://airate.tech
AppSupportURL=https://t.me/egotrippintg
DefaultDirName={localappdata}\Programs\AIRate
DefaultGroupName=AIRate
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=AIRate-Setup-{#AppVersion}
SetupIconFile=..\assets\airate.ico
UninstallDisplayIcon={app}\AI-Mentions.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
UninstallDisplayName=AIRate
Uninstallable=not IsPortableUpdate
CreateUninstallRegKey=not IsPortableUpdate

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
; build-installer.ps1 rejects top-level user data before compilation. Never
; exclude nested data folders: browser fingerprint libraries require them.
Source: "{#BundleDir}\*"; DestDir: "{app}"; Excludes: "account-url.txt,agent-version.txt"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BundleDir}\account-url.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "installed-mode.txt"; DestDir: "{app}"; Flags: ignoreversion; Check: not UpdatePortable
Source: "{#BrowserDir}\*"; DestDir: "{app}\browser"; Flags: ignoreversion recursesubdirs createallsubdirs
; Written last: a failed replacement never advertises the new version.
Source: "{#BundleDir}\agent-version.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AIRate"; Filename: "{app}\AI-Mentions.exe"; WorkingDir: "{app}"; Check: not IsPortableUpdate
Name: "{autodesktop}\AIRate"; Filename: "{app}\AI-Mentions.exe"; WorkingDir: "{app}"; Tasks: desktopicon; Check: not IsPortableUpdate

[Run]
Filename: "{app}\AI-Mentions.exe"; Description: "Запустить AIRate"; Flags: nowait postinstall skipifsilent

[Code]
var
  UpdateMode: String;
  UpdateAck: String;
  UpdateAbort: String;
  UpdateResult: String;
  UpdateVersion: String;
  UpdatePid: Integer;
  UpdateHandle: THandle;
  UpdateParentExited: Boolean;
  UpdateLaunched: Boolean;

const
  SYNCHRONIZE = $00100000;
  WAIT_OBJECT_0 = 0;
  WAIT_TIMEOUT = 258;

function OpenProcess(DesiredAccess: LongWord; InheritHandle: Boolean; ProcessId: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function UpdatePortable: Boolean;
begin
  Result := CompareText(UpdateMode, 'portable') = 0;
end;

function IsPortableUpdate: Boolean;
begin
  Result := UpdatePortable;
end;

function InitializeSetup(): Boolean;
var
  Target: String;
begin
  UpdateMode := Lowercase(ExpandConstant('{param:UPDATEMODE|}'));
  UpdateAck := ExpandConstant('{param:UPDATEACK|}');
  UpdateAbort := ExpandConstant('{param:UPDATEABORT|}');
  UpdateResult := ExpandConstant('{param:UPDATERESULT|}');
  UpdateVersion := ExpandConstant('{param:UPDATEVERSION|}');
  Target := ExpandConstant('{param:UPDATETARGET|}');
  UpdatePid := StrToIntDef(ExpandConstant('{param:UPDATEPID|0}'), 0);
  Result := True;
  if UpdateMode <> '' then begin
    if (UpdateMode <> 'installed') and (UpdateMode <> 'portable') then Result := False;
    if (Target = '') or (not FileExists(AddBackslash(Target) + 'AI-Mentions.exe')) then Result := False;
    if (UpdatePid <= 0) or (UpdateAck = '') or (UpdateAbort = '') or (UpdateResult = '') or (UpdateVersion = '') then Result := False;
    if Result then begin
      UpdateHandle := OpenProcess(SYNCHRONIZE, False, UpdatePid);
      Result := UpdateHandle <> 0;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Count: Integer;
  WaitResult: LongWord;
begin
  Result := '';
  if UpdateMode <> '' then begin
    if not SaveStringToFile(UpdateAck, 'READY', False) then
      Result := 'ack_failed'
    else begin
      WaitResult := WAIT_TIMEOUT;
      for Count := 1 to 120 do begin
        if FileExists(UpdateAbort) then begin
          Result := 'cancelled';
          break;
        end;
        WaitResult := WaitForSingleObject(UpdateHandle, 250);
        if WaitResult = WAIT_OBJECT_0 then begin
          UpdateParentExited := True;
          if FileExists(UpdateAbort) then
            Result := 'cancelled';
          break;
        end;
      end;
      if (Result = '') and (WaitResult <> WAIT_OBJECT_0) then
        Result := 'timeout';
    end;
    if Result <> '' then SaveStringToFile(UpdateResult, 'error:' + Result, False);
    CloseHandle(UpdateHandle);
    UpdateHandle := 0;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and (UpdateMode <> '') then begin
    SaveStringToFile(UpdateResult, 'ready:' + UpdateVersion, False);
    UpdateLaunched := Exec(AddBackslash(WizardDirValue) + 'AI-Mentions.exe', '', WizardDirValue, SW_SHOWNORMAL, ewNoWait, ResultCode);
    if not UpdateLaunched then
      SaveStringToFile(UpdateResult, 'error:launch_failed', False);
  end;
end;

procedure DeinitializeSetup();
var
  ResultCode: Integer;
begin
  // Setup failed after the parent exited. Attempt the existing target; a complete
  // rollback of every file is not guaranteed. Cancellation/timeout leaves it alone.
  if (UpdateMode <> '') and UpdateParentExited and (not UpdateLaunched) and
     (not FileExists(UpdateAbort)) and FileExists(AddBackslash(WizardDirValue) + 'AI-Mentions.exe') then begin
    SaveStringToFile(UpdateResult, 'error:install_failed', False);
    Exec(AddBackslash(WizardDirValue) + 'AI-Mentions.exe', '', WizardDirValue, SW_SHOWNORMAL, ewNoWait, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
begin
  // Only remove this installation's optional autostart. User data stays intact.
  if CurUninstallStep = usUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
      'AI Mentions Agent', Command) then
      if CompareText(Command, '"' + ExpandConstant('{app}\AI-Mentions.exe') + '" --background') = 0 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'AI Mentions Agent');
end;
