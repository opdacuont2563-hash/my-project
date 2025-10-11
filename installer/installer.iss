[Setup]
AppName=SurgiBot
AppVersion=1.0
AppPublisher=NBL Hospital
DefaultDirName={pf}\SurgiBot
DefaultGroupName=SurgiBot
OutputDir=D:\PythonProject1\installer
OutputBaseFilename=SurgiBot-Setup
;SetupIconFile=D:\PythonProject1\app.ico   ; ← ทดสอบปิดชั่วคราว ถ้าผ่านค่อยเปิด

ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
DisableDirPage=no
DisableProgramGroupPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#ifexist "compiler:Languages\Thai.isl"
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"
#endif

[Files]
Source: "D:\PythonProject1\dist\SurgiBot Client.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\PythonProject1\dist\SurgiBot Server.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\PythonProject1\app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\PythonProject1\.env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\SurgiBot Client"; Filename: "{app}\SurgiBot Client.exe"; IconFilename: "{app}\app.ico"
Name: "{group}\SurgiBot Server"; Filename: "{app}\SurgiBot Server.exe"; IconFilename: "{app}\app.ico"
Name: "{userdesktop}\SurgiBot Client"; Filename: "{app}\SurgiBot Client.exe"; Tasks: desktopicon; IconFilename: "{app}\app.ico"

[Tasks]
Name: "desktopicon"; Description: "สร้างชอร์ตคัตบน Desktop"; GroupDescription: "ตัวเลือกเพิ่มเติม:"; Flags: unchecked

[Run]
Filename: "{app}\SurgiBot Client.exe"; Description: "เปิดโปรแกรมทันที"; Flags: nowait postinstall skipifsilent
