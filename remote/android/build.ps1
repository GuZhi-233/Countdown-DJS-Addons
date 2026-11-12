param([switch]$Install)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Sdk = "D:\Android\Sdk"
$JavaHome = "D:\Game\Minecraft\java\26"
$AndroidJar = Join-Path $Sdk "platforms\android-35\android.jar"
$BuildTools = Join-Path $Sdk "build-tools\35.0.0"
$Adb = Join-Path $Sdk "platform-tools\adb.exe"
$Build = Join-Path $Root "build"
$Source = Join-Path $Root "app\src\main"
$env:JAVA_HOME = $JavaHome

if (!(Test-Path $AndroidJar)) { throw "android.jar not found: $AndroidJar" }
if (!(Test-Path (Join-Path $BuildTools "aapt2.exe"))) { throw "build-tools not found: $BuildTools" }

if (Test-Path $Build) { Remove-Item $Build -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Build, (Join-Path $Build "gen"), (Join-Path $Build "classes"), (Join-Path $Build "dex") | Out-Null

Write-Host "[1/6] compile resources"
& (Join-Path $BuildTools "aapt2.exe") compile --dir (Join-Path $Source "res") -o (Join-Path $Build "res.zip")
if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed" }

Write-Host "[2/6] link resources"
& (Join-Path $BuildTools "aapt2.exe") link -o (Join-Path $Build "base.apk") -I $AndroidJar --manifest (Join-Path $Source "AndroidManifest.xml") --java (Join-Path $Build "gen") --min-sdk-version 24 --target-sdk-version 35 -R (Join-Path $Build "res.zip") --auto-add-overlay
if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed" }

Write-Host "[3/6] compile java"
$sources = @()
$sources += Get-ChildItem -Path (Join-Path $Source "java") -Recurse -Filter *.java | ForEach-Object { $_.FullName }
$sources += Get-ChildItem -Path (Join-Path $Build "gen") -Recurse -Filter *.java | ForEach-Object { $_.FullName }
& (Join-Path $JavaHome "bin\javac.exe") --release 11 -encoding UTF-8 -classpath $AndroidJar -d (Join-Path $Build "classes") $sources
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

Write-Host "[4/6] dex"
& (Join-Path $JavaHome "bin\jar.exe") cf (Join-Path $Build "classes.jar") -C (Join-Path $Build "classes") .
if ($LASTEXITCODE -ne 0) { throw "jar failed" }
& (Join-Path $BuildTools "d8.bat") --release --min-api 24 --lib $AndroidJar --output (Join-Path $Build "dex") (Join-Path $Build "classes.jar")
if ($LASTEXITCODE -ne 0) { throw "d8 failed" }

Write-Host "[5/6] package and align"
$script = "import shutil, zipfile; shutil.copyfile(r'$Build\base.apk', r'$Build\unsigned.apk'); z = zipfile.ZipFile(r'$Build\unsigned.apk', 'a', zipfile.ZIP_DEFLATED); z.write(r'$Build\dex\classes.dex', 'classes.dex'); z.close()"
python -c $script
if ($LASTEXITCODE -ne 0) { throw "dex injection failed" }
& (Join-Path $BuildTools "zipalign.exe") -f 4 (Join-Path $Build "unsigned.apk") (Join-Path $Build "aligned.apk")
if ($LASTEXITCODE -ne 0) { throw "zipalign failed" }

Write-Host "[6/6] sign"
$Keystore = Join-Path $Root "debug.keystore"
if (!(Test-Path $Keystore)) {
    & (Join-Path $JavaHome "bin\keytool.exe") -genkeypair -keystore $Keystore -storepass android -alias androiddebugkey -keypass android -dname "CN=Android Debug,O=Android,C=US" -keyalg RSA -keysize 2048 -validity 10000
    if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
}
$Apk = Join-Path $Root "zx_remote.apk"
& (Join-Path $BuildTools "apksigner.bat") sign --ks $Keystore --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out $Apk (Join-Path $Build "aligned.apk")
if ($LASTEXITCODE -ne 0) { throw "apksigner failed" }
& (Join-Path $BuildTools "apksigner.bat") verify --verbose $Apk
if ($LASTEXITCODE -ne 0) { throw "apksigner verify failed" }
Write-Host "APK: $Apk"

if ($Install) {
    & $Adb install -r $Apk
    if ($LASTEXITCODE -ne 0) { throw "adb install failed" }
    & $Adb shell am start -n "com.miaoruixuan.zxremote/.MainActivity"
}
