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
#define AppVersion "1.0.4"
#define AppPublisher "Rizviz International Impex"
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
VersionInfoCopyright=Copyright (C) Rizviz International Impex. All rights reserved.
AppCopyright=Copyright (C) Rizviz International Impex. All rights reserved.
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

  // Google's own offline installer for businesses (64-bit MSI): installs Chrome for
  // every user, silently, and keeps it updating. Fetched at install time from Google,
  // so this setup does not carry or redistribute Chrome itself.
  ChromeUrl = 'https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi';
  ChromeMsiName = 'chrome-enterprise-x64.msi';

var
  CredPage: TInputFileWizardPage;
  DownloadPage: TDownloadWizardPage;
  ChromeMsi: String; // downloaded installer, '' when not needed or not available

function ChromeInstalled: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')
    or RegKeyExists(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')
    or FileExists(ExpandConstant('{commonpf64}\Google\Chrome\Application\chrome.exe'))
    or FileExists(ExpandConstant('{commonpf32}\Google\Chrome\Application\chrome.exe'))
    or FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe'));
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

// Fetch Chrome's installer before the install starts, with a progress bar.
// Never blocks the install: without internet, Chrome is simply asked for at the end.
procedure DownloadChromeWithProgress;
begin
  DownloadPage.Clear;
  DownloadPage.Add(ChromeUrl, ChromeMsiName, '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      ChromeMsi := ExpandConstant('{tmp}\' + ChromeMsiName);
    except
      ChromeMsi := '';
      Log('Chrome download failed: ' + GetExceptionMessage);
    end;
  finally
    DownloadPage.Hide;
  end;
end;

// The same without a window, for /SILENT installs (pages are not shown there).
procedure DownloadChromeQuietly;
begin
  try
    DownloadTemporaryFile(ChromeUrl, ChromeMsiName, '', nil);
    ChromeMsi := ExpandConstant('{tmp}\' + ChromeMsiName);
  except
    ChromeMsi := '';
    Log('Chrome download failed: ' + GetExceptionMessage);
  end;
end;

// Installs Chrome for all users from the downloaded MSI. True when Chrome is there afterwards.
function InstallChrome: Boolean;
var
  Code: Integer;
begin
  if ChromeMsi <> '' then begin
    WizardForm.StatusLabel.Caption := 'Installing Google Chrome (needed to visit the portals)...';
    Exec(ExpandConstant('{sys}\msiexec.exe'), '/i "' + ChromeMsi + '" /qn /norestart', '',
      SW_HIDE, ewWaitUntilTerminated, Code);
    Log('Chrome install exit code ' + IntToStr(Code));
  end;
  Result := ChromeInstalled;
end;

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
  DownloadPage := CreateDownloadPage('Downloading Google Chrome',
    'Scraping Hub uses Google Chrome to visit the portals. This PC does not have it yet, so it is being downloaded from Google.',
    @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Path: String;
begin
  Result := True;
  if (CurPageID = wpReady) and not ChromeInstalled then begin
    DownloadChromeWithProgress;
    Exit;
  end;
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

// Everything support needs, as one zip on the shared Desktop (C:\Users\Public\Desktop,
// so it shows for whoever is signed in, even when an admin account ran the setup).
// The person sends one file and never has to find ProgramData. '' if it could not be made.
function SaveSupportFile: String;
var
  Code: Integer;
  Zip: String;
begin
  Zip := ExpandConstant('{commondesktop}\Scraping Hub support.zip');
  DeleteFile(Zip);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "Compress-Archive -Path ''' + DataDir + '\logs\*'' -DestinationPath ''' + Zip + ''' -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  if FileExists(Zip) then
    Result := Zip
  else
    Result := '';
end;

// A problem in plain words; the details go to support as one file, not to the person.
procedure ReportProblem(const What: String);
var
  Zip, Tail: String;
begin
  if WizardSilent then
    Exit;
  Zip := SaveSupportFile;
  if Zip <> '' then
    Tail := 'Please send Rizviz support the file "Scraping Hub support.zip" that is now on your Desktop.'
  else
    Tail := 'Please tell Rizviz support, with the name of this PC.';
  MsgBox(What + #13#10#13#10 + 'Running this setup again often fixes it. If it does not, ' + Tail, mbError, MB_OK);
end;

function RunDatabaseSetup: Integer;
var
  Code: Integer;
begin
  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\setup-database.ps1') +
      '" -InstallDir "' + ExpandConstant('{app}') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := Code
  else
    Result := -1;
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

  // One automatic retry: a first start of the database service can be slow
  // (antivirus scanning the new files). The script is safe to run twice.
  WizardForm.StatusLabel.Caption := 'Preparing Scraping Hub''s database...';
  Code := RunDatabaseSetup;
  if Code <> 0 then begin
    WizardForm.StatusLabel.Caption := 'Preparing Scraping Hub''s database (second try)...';
    Sleep(5000);
    Code := RunDatabaseSetup;
  end;
  if Code <> 0 then begin
    ReportProblem('Scraping Hub was installed, but it could not prepare its database on this PC.');
    Exit; // the engine check below cannot pass without a database: one message is enough
  end;

  // Chrome: installed here if it was missing (downloaded before the install began).
  if not ChromeInstalled then begin
    if (ChromeMsi = '') and WizardSilent then
      DownloadChromeQuietly;
    if not InstallChrome then begin
      if not WizardSilent then
        MsgBox('One more step: please install Google Chrome (google.com/chrome).' + #13#10#13#10 +
          'Scraping Hub could not install it automatically (is this PC connected to the internet?). ' +
          'Once Chrome is installed, Scraping Hub is ready to use.',
          mbInformation, MB_OK);
      Exit; // the engine check opens Chrome, so it would only fail
    end;
  end;

  // Prove the engine runs on this PC before the person ever opens it. The result
  // goes to logs\self-check.log, so a failure arrives with its reason attached.
  WizardForm.StatusLabel.Caption := 'Checking that everything works (about half a minute)...';
  if not Exec(ExpandConstant('{cmd}'),
      '/C ""' + ExpandConstant('{app}\server\scraping-hub-server.exe') + '" --self-check > "' +
      DataDir + '\logs\self-check.log" 2>&1"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    ReportProblem('Scraping Hub was installed, but its final check did not pass on this PC.');
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
