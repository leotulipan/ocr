@echo off
echo Installing OCR tool globally...

REM Build the wheel package
echo Building wheel package...
uv build --wheel

REM Install globally using uv tool (use latest built wheel)
echo Installing globally...
for %%f in (dist\ocr-*.whl) do set WHEEL=%%f
uv tool install "%WHEEL%"

REM Update shell PATH
echo Updating shell PATH...
uv tool update-shell

echo.
echo Installation complete!
echo You can now use 'ocr --help' from any terminal.
echo.
echo To uninstall, run: uv tool uninstall ocr
pause
