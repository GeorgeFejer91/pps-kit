# Android Emulator Verification Protocol

Use this protocol only when the installer or hosted dashboard needs Android-device evidence, such as a mobile browser/WebView smoke of the public download page or local dashboard shell. It is not a replacement for the Windows installer smoke or hardware lab validation.

## Fresh-PC SDK Bootstrap

The Windows build-machine prerequisites are still Python, Go, and Java. On a fresh PC, install Java if Android SDK tools are needed:

```powershell
winget install --id EclipseAdoptium.Temurin.17.JDK --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
```

Install Android command-line tools under an ignored local SDK root such as `local_data/android_sdk`; do not commit SDK, AVD, APK, screenshots, or logcat artifacts. Required packages for emulator work are:

```powershell
$sdk = Resolve-Path .\local_data\android_sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:ANDROID_HOME = $sdk
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"
$env:Path = "$env:JAVA_HOME\bin;$sdk\cmdline-For-AI\engineering\tooling\latest\bin;$sdk\platform-tools;$env:Path"

sdkmanager "platform-tools" "emulator" "platforms;android-35" "build-tools;35.0.0"
sdkmanager "system-images;android-35;google_atd;x86_64"
```

Create AVDs under ignored local data:

```powershell
$env:ANDROID_AVD_HOME = (Resolve-Path .\local_data).Path + "\android_avd"
avdmanager create avd --name pps_api35_google_atd_x86_64 --package "system-images;android-35;google_atd;x86_64" --device pixel --force
```

## Acceleration Gate

Check acceleration before boot attempts:

```powershell
.\local_data\android_sdk\emulator\emulator.exe -accel-check
```

On Windows x86_64 hosts, Android `x86_64` emulator images require hardware acceleration. If the check reports `Android Emulator hypervisor driver is not installed on this machine`, install an acceleration provider before expecting the emulator to boot.

The SDK package is:

```powershell
sdkmanager "extras;google;Android_Emulator_Hypervisor_Driver"
```

Driver installation requires an elevated/admin shell:

```powershell
pushd .\local_data\android_sdk\extras\google\Android_Emulator_Hypervisor_Driver
.\silent_install_safe.bat
sc.exe query aehd
popd
```

If `sc.exe query aehd` reports service `1060`, the driver is not installed even if the batch file returned `0`. Re-run from an elevated shell or enable a supported Windows hypervisor path, then repeat `emulator -accel-check`.

## Boot And Evidence

Use a dedicated emulator port pair and explicit serial so connected physical devices do not pollute the evidence:

```powershell
$sdk = Resolve-Path .\local_data\android_sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_AVD_HOME = (Resolve-Path .\local_data).Path + "\android_avd"

Start-Process -WindowStyle Hidden -FilePath "$sdk\emulator\emulator.exe" -ArgumentList @(
  "-avd", "pps_api35_google_atd_x86_64",
  "-ports", "5580,5581",
  "-no-window",
  "-no-audio",
  "-no-snapshot",
  "-no-boot-anim",
  "-gpu", "swiftshader_indirect",
  "-no-metrics"
) -PassThru

.\local_data\android_sdk\platform-For-AI\engineering\tooling\adb.exe -s emulator-5580 shell getprop sys.boot_completed
```

For dashboard/download-page evidence, serve the repo or installed payload locally and reach the host from the emulator at `10.0.2.2`:

```powershell
.\.venv\Scripts\python.exe -m http.server 8787 --bind 0.0.0.0 --directory .
.\local_data\android_sdk\platform-For-AI\engineering\tooling\adb.exe -s emulator-5580 shell am start -a android.intent.action.VIEW -d http://10.0.2.2:8787/
.\local_data\android_sdk\platform-For-AI\engineering\tooling\adb.exe -s emulator-5580 exec-out screencap -p > .\local_data\android_emulator_pps_dashboard.png
.\local_data\android_sdk\platform-For-AI\engineering\tooling\adb.exe -s emulator-5580 shell uiautomator dump /sdcard/window.xml
.\local_data\android_sdk\platform-For-AI\engineering\tooling\adb.exe -s emulator-5580 exec-out cat /sdcard/window.xml > .\local_data\android_emulator_window.xml
```

Record at least SDK tool versions, emulator serial, model/API, URL under test, screenshot path, UI dump path, logcat path when collected, and whether the result was emulator evidence or physical-device evidence.

## 2026-06-25 Fresh-PC Result

The fresh-PC attempt installed local SDK tools and images. The current emulator was blocked without acceleration, but an archived emulator produced a usable boot path:

- `adb.exe version`: platform-tools `37.0.0`.
- `emulator.exe -version`: Android emulator `36.6.11.0`.
- `sdkmanager --version`: `21.0`.
- Installed local images included `system-images;android-35;google_apis;x86_64`, `system-images;android-35;google_atd;x86_64`, and `system-images;android-35;aosp_atd;arm64-v8a`.
- Windows firmware virtualization support was present, but `emulator -accel-check` reported `Android Emulator hypervisor driver is not installed on this machine`.
- The shell was not elevated (`IS_ADMIN=False`), and `silent_install_safe.bat` did not install the `aehd` service; `sc.exe query aehd` returned service `1060`.
- Current `x86_64` Google APIs and Google ATD AVDs exited or stayed offline before completing boot, with the warning `x86_64 emulation may not work without hardware acceleration`.
- The ARM64 ATD image is not a viable x86_64-host fallback: the emulator exited with `Avd's CPU Architecture 'arm64' is not supported by the QEMU2 emulator on x86_64 host. System image must match the host architecture.`
- A non-admin fallback booted after downloading Google's archived Windows emulator `32.1.11.0` (`emulator-windows_x64-9536276.zip`) into ignored `local_data/` and creating/running `system-images;android-30;google_atd;x86` with `-accel off`. The booted serial was `emulator-5620`, model `Android SDK built for x86`, Android `11`, API `30`, display `480x800`, density `240`, and `sys.boot_completed=1`.
- The API 30 ATD image contained `com.android.webview` but no full browser package. A mobile-page smoke therefore needs a small WebView probe APK or a browser APK before it can render `http://10.0.2.2:<port>/`.
- A physical ADB device was visible as `3487C10J0P01ZY device product:panther model:Quest_3S`, but that is not emulator evidence and should not be substituted for an emulator pass unless the user explicitly asks for physical-device verification.

Current Android-page blocker: the emulator can boot through the archived-emulator/API30-x86 fallback, but the WebView/browser probe still needs to be completed before claiming hosted download-page or dashboard rendering proof. For modern/current x86_64 emulator images, install an Android emulator acceleration provider from an elevated/admin shell.
