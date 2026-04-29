@echo off
REM ============================================================
REM  Seamless Production House — PyInstaller build script
REM  Python is at C:\Python313\python.exe (not on PATH)
REM ============================================================

SET PYTHON=C:\Python313\python.exe
SET NAME=SeamlessProductionHouse

echo [1/3] Installing / updating dependencies...
"%PYTHON%" -m pip install -r requirements.txt --quiet

echo [2/3] Running PyInstaller...
"%PYTHON%" -m PyInstaller ^
    --onefile ^
    --windowed ^
    --noconsole ^
    --name "%NAME%" ^
    --icon NONE ^
    --add-data "src;src" ^
    --hidden-import customtkinter ^
    --hidden-import tkinterdnd2 ^
    --hidden-import cv2 ^
    --hidden-import PIL ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import requests ^
    --hidden-import psutil ^
    --hidden-import numpy ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    main.py

echo [3/3] Done!
echo.
echo Output: dist\%NAME%.exe
echo.
echo Drop the .exe into any folder and run it.
echo RIFE and FFmpeg will be downloaded on first launch.
pause
