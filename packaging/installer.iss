; Windows installer for Coptic OCR, built by packaging/build.py with Inno Setup 6 (free):
;   ISCC.exe /DAppVersion=0.1.0 packaging\installer.iss
; It installs the folder PyInstaller made (dist\CopticOCR), with Start-menu and desktop
; shortcuts and an uninstaller. No administrator rights are needed: by default it installs for
; the current user, and offers all users to those who can.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F0C1B7E-3A52-4C8E-9C0B-C0F71C0C2A11}
AppName=Coptic OCR
AppVersion={#AppVersion}
AppVerName=Coptic OCR {#AppVersion}
AppPublisher=Mishel Makram
AppPublisherURL=https://github.com/mishelmakram/coptic-ocr
AppSupportURL=https://github.com/mishelmakram/coptic-ocr/issues
AppUpdatesURL=https://github.com/mishelmakram/coptic-ocr/releases
DefaultDirName={autopf}\Coptic OCR
DefaultGroupName=Coptic OCR
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=CopticOCR-{#AppVersion}-setup
SetupIconFile=..\src\copticocr\assets\copticocr.ico
UninstallDisplayIcon={app}\CopticOCR.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=auto

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\CopticOCR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Coptic OCR"; Filename: "{app}\CopticOCR.exe"
Name: "{autodesktop}\Coptic OCR"; Filename: "{app}\CopticOCR.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CopticOCR.exe"; Description: "{cm:LaunchProgram,Coptic OCR}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Models from an earlier version, so the program does not pick an old one.
Type: filesandordirs; Name: "{app}\models"
