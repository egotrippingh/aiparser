#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputPath
  #error OutputPath is required
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
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=AIRate

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
; build-installer.ps1 rejects top-level user data before compilation. Never
; exclude nested data folders: browser fingerprint libraries require them.
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed-mode.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AIRate"; Filename: "{app}\AI-Mentions.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\AIRate"; Filename: "{app}\AI-Mentions.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AI-Mentions.exe"; Description: "Запустить AIRate"; Flags: nowait postinstall skipifsilent

[Code]
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
