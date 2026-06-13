!ifndef APP_VERSION
!define APP_VERSION "dev"
!endif

!ifndef SOURCE_DIR
!define SOURCE_DIR "..\..\dist\dst-deployer-qt-windows"
!endif

!ifndef OUT_FILE
!define OUT_FILE "..\..\dist\dst-deployer-qt-windows.exe"
!endif

Name "DST Deployer"
OutFile "${OUT_FILE}"
RequestExecutionLevel user
Unicode true
SilentInstall silent
AutoCloseWindow true
ShowInstDetails nevershow

VIProductVersion "0.0.0.0"
VIAddVersionKey "ProductName" "DST Deployer"
VIAddVersionKey "CompanyName" "DreamReflex"
VIAddVersionKey "FileDescription" "DST Deployer portable launcher"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"

Section
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /r "${SOURCE_DIR}\*"
  ExecWait '"$PLUGINSDIR\dst-deployer-qt.exe"'
SectionEnd

