$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$AndroidProject = Join-Path $Root "android\runner-companion"
$Gradle = Join-Path $AndroidProject "gradlew.bat"

if (-not (Test-Path $Gradle)) {
  throw "Android Gradle wrapper was not found: $Gradle"
}

if (-not $env:JAVA_HOME) {
  $JdkCandidates = @(
    "C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot",
    "C:\Program Files\Android\Android Studio\jbr"
  ) + @(Get-ChildItem "C:\Program Files\Microsoft" -Directory -Filter "jdk-17*" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
  foreach ($Candidate in $JdkCandidates) {
    if ($Candidate -and (Test-Path (Join-Path $Candidate "bin\java.exe"))) {
      $env:JAVA_HOME = $Candidate
      break
    }
  }
}
if ($env:JAVA_HOME) {
  $env:PATH = (Join-Path $env:JAVA_HOME "bin") + ";$env:PATH"
}

if (-not $env:ANDROID_HOME -and -not $env:ANDROID_SDK_ROOT) {
  $SdkCandidates = @(
    (Join-Path $Root "local_data\android_sdk"),
    (Join-Path $env:LOCALAPPDATA "Android\Sdk"),
    "C:\Android\Sdk"
  )
  foreach ($Candidate in $SdkCandidates) {
    if ($Candidate -and (Test-Path $Candidate)) {
      $env:ANDROID_HOME = $Candidate
      $env:ANDROID_SDK_ROOT = $Candidate
      break
    }
  }
}
if ($env:ANDROID_HOME) {
  $env:PATH = (Join-Path $env:ANDROID_HOME "platform-tools") + ";$env:PATH"
}

Push-Location $AndroidProject
try {
  & $Gradle assembleDebug
  if ($LASTEXITCODE -ne 0) {
    throw "Android companion Gradle build failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
