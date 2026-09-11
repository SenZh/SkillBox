; SkillBox Windows 安装包脚本 (Inno Setup 6)
;
; 编译方式（推荐由 tools/build_release.py 自动调用）：
;   ISCC.exe /DMyAppVersion=0.2.0 /DSourceDir=<绿色目录> /DOutputDir=<输出目录> tools/installer.iss
;
; 说明：安装到当前用户目录（默认无需管理员权限），写入开始菜单与可选桌面快捷方式。

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\release\SkillBox-" + MyAppVersion + "-win64"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

#define MyAppName "SkillBox"
#define MyAppPublisher "SenZh"
#define MyAppURL "https://github.com/SenZh/SkillBox"
#define MyAppExeName "SkillBox.exe"

[Setup]
AppId={{9F2A7C1E-3B4D-4E6A-9C21-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 默认安装到当前用户（无需管理员），若需全局安装可去掉 PrivilegesRequiredOverridesAllowed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=SkillBox-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableWelcomePage=no

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; 复制绿色目录下的全部内容（exe + 文档 + 资源 + 内置技能）
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载前尝试关闭正在运行的托盘应用，避免文件占用
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; Flags: runhidden; RunOnceId: "KillSkillBox"
