; Lite Game Recorder v1.5 — Inno Setup installer script
; Makes a real Windows installer (Setup.exe) with Desktop icon,
; Start Menu entry and an uninstaller — like any normal app.
;
; How to use (on Windows, after building the .exe once):
;   1. Double-click "Install Lite Game Recorder.bat" — it builds
;      dist\LiteGameRecorder.exe and installs it for you.
;      (That is the easy way; you do not need this file.)
;   2. OR, to make a shareable Setup.exe: install Inno Setup
;      (free, jrsoftware.org/isdl.php), open this file in it
;      and press Build. It creates LiteGameRecorder-Setup-v2.3.exe
;      in the Output folder.
; The installer itself needs dist\LiteGameRecorder.exe to exist.

#define MyAppName "Lite Game Recorder"
#define MyAppVersion "2.3"
#define MyAppPublisher "Lite Game Recorder"
#define MyAppExeName "LiteGameRecorder.exe"

[Setup]
AppId={{8F3A2C1D-4E5B-4A6C-9D7E-1A2B3C4D5E6F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=LiteGameRecorder-Setup-v2.3
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
