@echo off
title Build PokéChamps bHaptics Tactile Link
cd /d "%~dp0"
echo ========================================================
echo   Building Pochams bHaptics Executable (PyInstaller)
echo ========================================================
pyinstaller --noconfirm --onedir --windowed --name "Pochams_bHaptics" ^
  --hidden-import "bhaptics_python" --collect-all "bhaptics_python" ^
  --hidden-import "rapidocr_onnxruntime" --collect-all "rapidocr_onnxruntime" ^
  --hidden-import "onnxruntime" --collect-all "onnxruntime" ^
  main.py
echo.
echo ========================================================
echo   Build Finished! Output is in dist/Pochams_bHaptics/
echo ========================================================
pause
