@echo off
echo Installing OCR tool globally...

REM Build the wheel package
echo Building wheel package...
uv build --wheel

REM Install globally using uv tool
echo Installing globally...
uv tool install dist/ocr-0.1.0-py3-none-any.whl

REM Update shell PATH
echo Updating shell PATH...
uv tool update-shell

echo.
echo Installation complete!
echo You can now use 'ocr --help' from any terminal.
echo.
echo To uninstall, run: uv tool uninstall ocr
pause
