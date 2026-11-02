; Inno Setup script: per-user installer of the FTTx BOM Tool (no administrator rights needed).
; Build:  iscc /DAppVersion=0.8.0 packaging\installer.iss   (after pyinstaller, from the fttx_bom folder)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2A4E-8B7D-4B7A-9E31-2C5D0F7A1B93}
AppName=FTTx BOM Tool
AppVersion={#AppVersion}
AppVerName=FTTx BOM Tool {#AppVersion}
DefaultDirName={localappdata}\Programs\FTTx BOM Tool
DefaultGroupName=FTTx BOM Tool
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FTTx-BOM-Tool-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\FTTx BOM Tool.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\FTTx BOM Tool\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\FTTx BOM Tool"; Filename: "{app}\FTTx BOM Tool.exe"
Name: "{userdesktop}\FTTx BOM Tool"; Filename: "{app}\FTTx BOM Tool.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\FTTx BOM Tool.exe"; Description: "Start FTTx BOM Tool"; Flags: nowait postinstall skipifsilent
