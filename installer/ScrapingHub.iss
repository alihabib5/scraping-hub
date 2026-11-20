; Scraping Hub — Windows setup wizard (Inno Setup 6).
;
;   1. server\.venv\Scripts\python.exe installer\build_server.py
;   2. client:  SCRAPING_HUB_DESKTOP=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:9001 npx next build
;   3. desktop: npm run package
;   4. server\.venv\Scripts\python.exe installer\stage.py
;   5. ISCC installer\ScrapingHub.iss   ->  installer\output\ScrapingHub-Setup-<version>.exe
;
; Installs to C:\Program Files\Scraping Hub (app, read-only) and keeps everything the
; app writes in C:\ProgramData\Scraping Hub. Asks for the encrypted credentials file
; (installer\make_credentials.py). Updating = running a newer setup: same AppId, so it
; upgrades in place and keeps the database, results and credentials.

#define AppName "Scraping Hub"
#define AppVersion "1.0.0"
#define AppPublisher "Rizviz"
#define AppExe "Scraping Hub.exe"
#ifndef Stage
#define Stage "build\stage"
#endif

[Setup]
; Never change AppId: it is how a newer setup recognises an installed copy to upgrade.
AppId={{6B1F4C1E-8F2A-4D5B-9C3E-2A7D5E0F1B94}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupIconFile=scraping-hub.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=output
OutputBaseFilename=ScrapingHub-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
VersionInfoCompany={#AppPublisher}
VersionInfoProductName={#AppName}
VersionInfoVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; Everyone who uses this PC can write here; the app runs as the normal user.
Name: "{commonappdata}\{#AppName}"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
const
  CredName = 'credentials.shc';
  DbService = 'ScrapingHubDB';

var
  CredPage: TInputFileWizardPage;

// An ARM PC runs this x64 build through emulation, where the engine has
// failed with "illegal instruction". Warn before wasting a long install.
function InitializeSetup: Boolean;
begin
  Result := True;
  if IsArm64 and not WizardSilent then
    Result := MsgBox('This PC has an ARM processor. Scraping Hub is built for ordinary (x64) Windows PCs ' +
      'and is not expected to work here yet.' + #13#10#13#10 + 'Install anyway?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

function DataDir: String;
begin
  Result := ExpandConstant('{commonappdata}\{#AppName}');
end;

function HaveCredentials: Boolean;
begin
  Result := FileExists(DataDir + '\' + CredName);
end;

function IsCredentialsFile(const Path: String): Boolean;
var
  Data: AnsiString;
begin
  Result := LoadStringFromFile(Path, Data) and (Copy(Data, 1, 4) = 'SHC1');
end;

procedure InitializeWizard;
var
  Hint: String;
begin
  if HaveCredentials then
    Hint := 'This PC already has a credentials file. Leave this empty to keep it, or choose a new one to replace it.'
  else
    Hint := 'Choose the credentials file you were given with this setup (it ends in .shc).';
  CredPage := CreateInputFilePage(wpSelectTasks,
    'Credentials file',
    'Scraping Hub signs in to the procurement portals with the logins in this file.',
    Hint);
  CredPage.Add('Credentials file:', 'Scraping Hub credentials (*.shc)|*.shc|All files|*.*', '.shc');
  CredPage.Values[0] := ExpandConstant('{param:CREDENTIALS|}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Path: String;
begin
  Result := True;
  if CurPageID <> CredPage.ID then
    Exit;
  Path := Trim(CredPage.Values[0]);
  if (Path = '') and HaveCredentials then
    Exit;
  if Path = '' then begin
    MsgBox('Please choose the credentials file you were given. Without it Scraping Hub cannot sign in to the portals.', mbError, MB_OK);
    Result := False;
  end else if not FileExists(Path) then begin
    MsgBox('That file does not exist:' + #13#10 + Path, mbError, MB_OK);
    Result := False;
  end else if not IsCredentialsFile(Path) then begin
    MsgBox('That is not a Scraping Hub credentials file. Please choose the .shc file you were given.', mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  // On an upgrade the database service is running from files about to be replaced.
  Exec(ExpandConstant('{sys}\sc.exe'), 'stop ' + DbService, '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(2000);
  Result := '';
end;

function ChromeInstalled: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')
    or RegKeyExists(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Path: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  Path := Trim(CredPage.Values[0]);
  if Path <> '' then
    if not FileCopy(Path, DataDir + '\' + CredName, False) then
      MsgBox('Could not copy the credentials file. Run the setup again to retry.', mbError, MB_OK);

  // PostgreSQL needs the Visual C++ runtime, so it goes in first, right here:
  // [Run] entries are not guaranteed to run before this step.
  // Exit codes 1638 (a newer one is installed) and 3010 (reboot later) are fine.
  WizardForm.StatusLabel.Caption := 'Installing Microsoft Visual C++ runtime...';
  Exec(ExpandConstant('{app}\tools\vcredist_x64.exe'), '/install /quiet /norestart', '',
    SW_HIDE, ewWaitUntilTerminated, Code);

  WizardForm.StatusLabel.Caption := 'Setting up the Scraping Hub database...';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\setup-database.ps1') +
      '" -InstallDir "' + ExpandConstant('{app}') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    MsgBox('The Scraping Hub database could not be set up (code ' + IntToStr(Code) + ').' + #13#10 +
      'Please send IT this file:' + #13#10 + DataDir + '\logs\setup-database.log', mbError, MB_OK);

  // Prove the engine runs on this PC before the user ever opens it. The result
  // goes to logs\self-check.log, so a failure arrives with its reason attached.
  WizardForm.StatusLabel.Caption := 'Checking the installation (about half a minute)...';
  if not Exec(ExpandConstant('{cmd}'),
      '/C ""' + ExpandConstant('{app}\server\scraping-hub-server.exe') + '" --self-check > "' +
      DataDir + '\logs\self-check.log" 2>&1"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    MsgBox('Scraping Hub was installed, but its engine did not pass the self-check on this PC (code ' + IntToStr(Code) + ').' + #13#10 +
      'Please send IT these files:' + #13#10 + DataDir + '\logs\self-check.log' + #13#10 + DataDir + '\logs\setup-database.log', mbError, MB_OK);

  if not ChromeInstalled and not WizardSilent then
    MsgBox('Google Chrome was not found on this PC. Scraping Hub uses Chrome to visit the portals, ' +
      'so please install Chrome before your first run.', mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
  Args: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  Args := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\remove-database.ps1') +
    '" -InstallDir "' + ExpandConstant('{app}') + '"';
  if not UninstallSilent and (MsgBox('Also delete all Scraping Hub data on this PC (database, results, downloaded documents, credentials)?' + #13#10#13#10 +
      'Choose No to keep it: reinstalling later will pick it all up again.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
    Args := Args + ' -DeleteData';
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;
