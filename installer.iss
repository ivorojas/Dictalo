; Instalador de Dictalo — Inno Setup
#define AppName "Dictalo"
#define AppVersion "1.0.0"
#define AppExe "Dictalo.exe"

[Setup]
AppId={{D1C7A10E-0001-4B91-9A55-DICTALOAPP001}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Ivo
DefaultDirName={localappdata}\Programs\Dictalo
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Dictalo-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos:"
Name: "startup"; Description: "Iniciar Dictalo al encender la PC"; GroupDescription: "Inicio:"

[Files]
Source: "dist\Dictalo\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir Dictalo ahora"; Flags: nowait postinstall skipifsilent
