!ifndef APP_VERSION
!define APP_VERSION "dev"
!endif

!ifndef SOURCE_DIR
!define SOURCE_DIR "..\..\dist\dst-deployer-qt-windows"
!endif

!ifndef OUT_FILE
!define OUT_FILE "..\..\dist\dst-deployer-qt-windows-installer.exe"
!endif

Name "DST Deployer"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\DST Deployer"
RequestExecutionLevel user
Unicode true

VIProductVersion "0.0.0.0"
VIAddVersionKey "ProductName" "DST Deployer"
VIAddVersionKey "CompanyName" "DreamReflex"
VIAddVersionKey "FileDescription" "DST Deployer Qt GUI"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"

Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*"
  CreateShortcut "$DESKTOP\DST Deployer.lnk" "$INSTDIR\dst-deployer-qt.exe"
  CreateDirectory "$SMPROGRAMS\DST Deployer"
  CreateShortcut "$SMPROGRAMS\DST Deployer\DST Deployer.lnk" "$INSTDIR\dst-deployer-qt.exe"
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\DST Deployer.lnk"
  Delete "$SMPROGRAMS\DST Deployer\DST Deployer.lnk"
  RMDir "$SMPROGRAMS\DST Deployer"
  RMDir /r "$INSTDIR"
SectionEnd

