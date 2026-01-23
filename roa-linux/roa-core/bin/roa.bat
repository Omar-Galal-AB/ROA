@echo off
REM ROA Launcher Script
set ROA_HOME=%~dp0..
set PYTHONPATH=%ROA_HOME%\lib;%PYTHONPATH%
python "%ROA_HOME%\lib\roa_main.py" %*
