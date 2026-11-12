$ErrorActionPreference = "Stop"
$Package = $PSScriptRoot
$Root = Split-Path -Parent (Split-Path -Parent $Package)
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build"
$Remote = Join-Path $Root "remote\windows"
$Icon = Join-Path $Root "assets\djstp.ico"
$Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if (!(Test-Path $Iscc)) { throw "Inno Setup not found: $Iscc" }

$text = Get-Content (Join-Path $Remote "version.py") -Raw
$match = [regex]::Match($text, 'VERSION = "([^"]+)"')
if (!$match.Success) { throw "version not found" }
$Version = $match.Groups[1].Value

if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Dist, $Work | Out-Null

python -m PyInstaller --noconfirm --clean --windowed --onedir --contents-directory . --name ZXRemote --icon $Icon --add-data "$Icon;." --distpath $Dist --workpath $Work --specpath $Work (Join-Path $Remote "main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

& $Iscc "/DMyAppVersion=$Version" (Join-Path $Package "ZXRemote.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

powershell -ExecutionPolicy Bypass -File (Join-Path $Root "remote\android\build.ps1")
if ($LASTEXITCODE -ne 0) { throw "Android build failed" }

$Installer = Join-Path $Dist "installer\ZXRemote_Setup_$Version.exe"
$Apk = Join-Path $Dist "installer\ZXRemote_$Version.apk"
$PluginZip = Join-Path $Dist "installer\ZX_Plugin_$Version.zip"
Copy-Item (Join-Path $Root "remote\android\zx_remote.apk") $Apk -Force
Compress-Archive -Path (Join-Path $Root "plugins\zx.py"), (Join-Path $Root "plugins\zx.json") -DestinationPath $PluginZip -Force

$hashFile = Join-Path $Dist "installer\SHA256SUMS.txt"
$lines = @()
foreach ($file in @($Installer, $Apk, $PluginZip)) {
    $hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower()
    $lines += "$hash  $(Split-Path -Leaf $file)"
}
$lines | Set-Content -Path $hashFile -Encoding ASCII

Write-Host "Installer: $Installer"
Write-Host "APK:       $Apk"
Write-Host "Plugin:    $PluginZip"
Write-Host "Checksums: $hashFile"
