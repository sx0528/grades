; GradeTracker 安装包脚本（Inno Setup 6）
; 使用方法：安装 Inno Setup 6 后，用 ISCC 编译本脚本，
; 或在 Inno Setup 图形界面打开本脚本点击 Build。
; 生成：GradeTracker-setup.exe 安装包

#define MyAppName "高考成绩追踪系统"
#define MyAppNameEn "GradeTracker"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Xin Song"
#define MyAppExeName "GradeTracker.exe"

[Setup]
AppId={{8E5B3C2A-9D4F-4E7B-A1C6-3F2D8B7E5A91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer
OutputBaseFilename=GradeTracker-setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
; 将 dist\GradeTracker 整个目录打入安装包
Source: "..\dist\GradeTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时保留用户数据目录（不指定 user_data 即默认保留）
