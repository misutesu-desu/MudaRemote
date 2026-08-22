$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$sdkPath = $env:ANDROID_HOME
if (-not $sdkPath) { $sdkPath = Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
if (-not (Test-Path (Join-Path $sdkPath 'platforms\android-35'))) {
    throw "Android SDK Platform 35 is required. Set ANDROID_HOME or install platform 35."
}
$env:ANDROID_HOME = $sdkPath
$gradlePath = Get-ChildItem (Join-Path $env:USERPROFILE '.gradle\wrapper\dists\gradle-8.11-bin') -Recurse -Filter gradle.bat -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if (-not $gradlePath) { throw "Gradle 8.11 was not found in the local wrapper cache." }
& $gradlePath ':app:assembleUx'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
