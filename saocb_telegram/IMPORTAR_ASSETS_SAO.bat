@echo off
setlocal
cd /d "%~dp0\.."
if "%~1"=="" (
  echo Arrastra sobre este BAT la carpeta SAO-CBTEST001 donde estan los split_InstallTimeAssetPack*.apk
  pause
  exit /b 1
)
python saocb_telegram\tools\importar_assets.py "%~1" --out saocb_telegram\imported_assets
pause
