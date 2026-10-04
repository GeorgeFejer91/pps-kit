!macro NSIS_HOOK_PREINSTALL
  IfFileExists "$INSTDIR\shared\*.*" 0 pps_shared_compatible
  IfFileExists "$INSTDIR\shared\pps-shared-v2-0.1.0.marker" pps_shared_compatible 0
  Abort "An incompatible PPS Shared component is already installed in this folder."
pps_shared_compatible:
!macroend

!macro NSIS_HOOK_POSTINSTALL
  CreateShortcut "$SMPROGRAMS\PPS Experiment Runner.lnk" "$INSTDIR\runner\pps-experiment-runner.exe"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  Delete "$SMPROGRAMS\PPS Experiment Runner.lnk"
!macroend
