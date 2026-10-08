param(
  [Parameter(Mandatory=$true)][string]$OriginalDir,
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [Parameter(Mandatory=$true)][string]$Keystore,
  [string]$Alias = "saocb",
  [string]$OutDir = ".\\SAO-CB-FINAL"
)
$ErrorActionPreference='Stop'
$names=@(
 'base.apk','split_config.arm64_v8a.apk','split_config.armeabi_v7a.apk',
 'split_config.de.apk','split_config.en.apk','split_config.xxhdpi.apk',
 'split_InstallTimeAssetPack.apk','split_InstallTimeAssetPack2.apk','split_InstallTimeAssetPack3.apk'
)
foreach($n in $names){ if(!(Test-Path (Join-Path $OriginalDir $n))){ throw "Falta $n" } }
if(!(Test-Path $Keystore)){ throw "No existe keystore: $Keystore" }
$apksigner=(Get-Command apksigner -ErrorAction SilentlyContinue).Source
if(!$apksigner){ throw 'apksigner no esta en PATH' }
$python=(Get-Command python -ErrorAction SilentlyContinue).Source
if(!$python){ throw 'python no esta en PATH' }
Remove-Item $OutDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $OutDir | Out-Null
foreach($n in $names){ Copy-Item (Join-Path $OriginalDir $n) (Join-Path $OutDir $n) }
$tmp=Join-Path $OutDir 'libcocos2dcpp.saocb.so'
& $python "$PSScriptRoot\patch_client_url.py" (Join-Path $PSScriptRoot 'libcocos2dcpp_SAO-CB_FRESH_FINAL.so') $ServerUrl $tmp
if($LASTEXITCODE -ne 0){ throw 'Fallo patch URL' }
$arm=Join-Path $OutDir 'split_config.arm64_v8a.apk'
$work=Join-Path $OutDir '_arm64'
New-Item -ItemType Directory -Path $work | Out-Null
Push-Location $work
jar xf $arm
Copy-Item $tmp '.\lib\arm64-v8a\libcocos2dcpp.so' -Force
Remove-Item $arm -Force
jar cf $arm .
Pop-Location
Remove-Item $work -Recurse -Force
Remove-Item $tmp -Force
foreach($n in $names){
 $p=Join-Path $OutDir $n
 & $apksigner sign --ks $Keystore --ks-key-alias $Alias $p
 if($LASTEXITCODE -ne 0){ throw "Fallo firma $n" }
 & $apksigner verify --verbose $p | Out-Null
 if($LASTEXITCODE -ne 0){ throw "Fallo verificacion $n" }
}
$bundle=Join-Path $OutDir 'SAO-CB-FINAL.apks'
Compress-Archive -Path ($names | ForEach-Object {Join-Path $OutDir $_}) -DestinationPath ($bundle+'.zip') -Force
Move-Item ($bundle+'.zip') $bundle -Force
Write-Host "OK: $bundle"
Write-Host 'Los 9 APK quedaron parcheados, firmados y verificados.'
