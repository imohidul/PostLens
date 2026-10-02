; Inno Setup script for the PostLens Windows installer.
; Built by GitHub Actions:  iscc /DAppVersion=1.0.1 packaging\windows\installer.iss
; Installs per-user (no administrator rights needed), adds a Start menu entry,
; an optional desktop shortcut, and a normal uninstaller.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B3F4E2A-9C1D-4C57-8E9B-2F7A5D3C1E40}
AppName=PostLens
AppVersion={#AppVersion}
AppVerName=PostLens {#AppVersion}
AppPublisher=imohidul
AppPublisherURL=https://github.com/imohidul/PostLens
AppSupportURL=https://github.com/imohidul/PostLens/issues
AppUpdatesURL=https://github.com/imohidul/PostLens/releases
DefaultDirName={localappdata}\Programs\PostLens
DefaultGroupName=PostLens
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=postlens
SetupIconFile=..\icons\icon.ico
UninstallDisplayIcon={app}\PostLens.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\..\LICENSE
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\PostLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PostLens"; Filename: "{app}\PostLens.exe"
Name: "{group}\Uninstall PostLens"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PostLens"; Filename: "{app}\PostLens.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PostLens.exe"; Description: "{cm:LaunchProgram,PostLens}"; Flags: nowait postinstall skipifsilent
; Automatic updates run this installer silently with /RELAUNCH=1, then reopen PostLens.
Filename: "{app}\PostLens.exe"; Flags: nowait; Check: ShouldRelaunch

; Your data (~\.postlens: analyses, settings, downloaded models) is kept on
; uninstall on purpose, so reinstalling or updating never loses it.

[Code]
// True only for a silent install started by PostLens's updater with /RELAUNCH=1.
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
