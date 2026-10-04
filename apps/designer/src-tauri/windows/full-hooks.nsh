!macro NSIS_HOOK_POSTINSTALL
  CreateShortcut "$SMPROGRAMS\PPS Experiment Runner.lnk" "$INSTDIR\runner\pps-experiment-runner.exe"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  Delete "$SMPROGRAMS\PPS Experiment Runner.lnk"
!macroend
