; Instalador de Dictado App (Inno Setup 6)
#define AppName "Dictado App"
#define AppVersion "1.2.2"
#define AppExe "DictadoApp.exe"

[Setup]
; Mismo AppId que la versión anterior ("Dictalo"): así este instalador la ACTUALIZA
; (reemplaza su entrada en Aplicaciones instaladas) en vez de dejar dos apps.
AppId={{D1C7A10E-0001-4B91-9A55-DICTALOAPP001}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Ivo Rojas
AppPublisherURL=https://github.com/ivorojas/dictado-app
DefaultDirName={localappdata}\Programs\{#AppName}
UsePreviousAppDir=no
DefaultGroupName={#AppName}
; Sin esto Inno reusa el grupo del menú Inicio de la instalación anterior ("Dictalo")
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=DictadoApp-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
; Si está abierta (esta versión o la anterior), pide cerrarla antes de instalar
AppMutex=Global\DictadoApp_SingleInstance,Global\Dictalo_SingleInstance
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos:"; Flags: unchecked
Name: "startup"; Description: "Iniciar {#AppName} al encender la PC"; GroupDescription: "Inicio:"

[InstallDelete]
; Restos de la versión anterior, que se llamaba "Dictalo"
Type: filesandordirs; Name: "{localappdata}\Programs\Dictalo"
Type: files; Name: "{userstartup}\Dictalo.lnk"
Type: files; Name: "{userdesktop}\Dictalo.lnk"
Type: filesandordirs; Name: "{userprograms}\Dictalo"

[Files]
Source: "dist\DictadoApp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent
