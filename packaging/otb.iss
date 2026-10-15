; Inno Setup script for the OTB Windows installer.
;
; Expects the PyInstaller output in dist\OTB (OTB.exe + _internal\) and is
; normally run by .github/workflows/windows-installer.yml:
;   iscc /DAppVersion=1.0 packaging\otb.iss
; The result is packaging\Output\OTB-Setup-<version>.exe.

#ifndef AppVersion
  #define AppVersion "0.0-dev"
#endif

#define AppName "Opening Tree Builder"
#define AppPublisher "GambitGear"
#define AppURL "https://github.com/malo1972/otb"
#define AppExe "OTB.exe"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades and the uninstaller.
AppId={{8F6A194C-F763-4BEA-9CA5-68F0600FA6A0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://www.gambitgear.ch
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
; Per-user install without an admin prompt (friendlier for beginners):
; {autopf} then resolves to %LOCALAPPDATA%\Programs.
PrivilegesRequired=lowest
DefaultDirName={autopf}\GambitGear\OTB
DefaultGroupName=GambitGear
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE.txt
SourceDir=.
OutputDir=Output
OutputBaseFilename=OTB-Setup-{#AppVersion}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=otb.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The whole PyInstaller folder: OTB.exe plus the bundled Python, Qt and libraries.
Source: "..\dist\OTB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Books and settings live in the user's profile (%APPDATA%\GambitGear\OTB and
; the registry), not in {app}, so uninstalling never deletes a user's book.
