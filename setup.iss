[Setup]
AppName=AXIS OS
AppVersion=1.3.2
AppVerName=AXIS OS 1.3.2
AppPublisher=AXIS
DefaultDirName={autopf}\AXIS OS
DefaultGroupName=AXIS OS
OutputDir=dist
OutputBaseFilename=AXIS_OS_Setup_1.3.2
SetupIconFile=data\icon_panel.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=AXIS OS
UninstallDisplayIcon={app}\AXIS_OS.exe
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon_panel";  Description: "Desktop shortcut: AXIS Panel";  GroupDescription: "Shortcuts:"
Name: "desktopicon_sphere"; Description: "Desktop shortcut: AXIS Sphere"; GroupDescription: "Shortcuts:"
Name: "desktopicon_ide";    Description: "Desktop shortcut: AXIS IDE";    GroupDescription: "Shortcuts:"
Name: "startuprun";         Description: "Run AXIS Panel on Windows startup"; GroupDescription: "Autostart:"

[Files]
; Only .exe, _internal, data, assets — NO .py or .bat files
Source: "dist\AXIS_OS\AXIS_OS.exe";     DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AXIS_OS\AXIS_Sphere.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AXIS_OS\AXIS_IDE.exe";    DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AXIS_OS\_internal\*";     DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AXIS_OS\data\*";          DestDir: "{app}\data";      Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AXIS_OS\assets\*";        DestDir: "{app}\assets";    Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "dist\AXIS_OS\version.txt";     DestDir: "{app}";           Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\AXIS Panel";        Filename: "{app}\AXIS_OS.exe";     IconFilename: "{app}\data\icon_panel.ico"
Name: "{group}\AXIS Sphere";       Filename: "{app}\AXIS_Sphere.exe"; IconFilename: "{app}\data\icon_sphere.ico"
Name: "{group}\AXIS IDE";          Filename: "{app}\AXIS_IDE.exe";    IconFilename: "{app}\data\icon_ide.ico"
Name: "{group}\Uninstall AXIS OS"; Filename: "{uninstallexe}"

; Desktop shortcuts (optional)
Name: "{commondesktop}\AXIS Panel";  Filename: "{app}\AXIS_OS.exe";     IconFilename: "{app}\data\icon_panel.ico";  Tasks: desktopicon_panel
Name: "{commondesktop}\AXIS Sphere"; Filename: "{app}\AXIS_Sphere.exe"; IconFilename: "{app}\data\icon_sphere.ico"; Tasks: desktopicon_sphere
Name: "{commondesktop}\AXIS IDE";    Filename: "{app}\AXIS_IDE.exe";    IconFilename: "{app}\data\icon_ide.ico";    Tasks: desktopicon_ide

[Registry]
; Autostart — runs Panel only (no .bat)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "AXIS OS"; \
    ValueData: """{app}\AXIS_OS.exe"""; \
    Flags: uninsdeletevalue; Tasks: startuprun

[Run]
Filename: "{app}\AXIS_OS.exe"; Description: "Launch AXIS Panel"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
