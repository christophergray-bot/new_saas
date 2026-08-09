@echo off
cd /d "%~dp0"
python -m unittest tests/test_security_11_15.py tests/test_security_16_20.py -v
set EXIT_CODE=%ERRORLEVEL%
echo.
if %EXIT_CODE% EQU 0 (
  echo All local security tests passed.
) else (
  echo One or more security tests failed. Review the output above.
)
pause
exit /b %EXIT_CODE%
