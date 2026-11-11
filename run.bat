@echo off
chcp 65001 >nul
title KinoBudka
cd /d "%~dp0"

rem Запуск KinoBudka на Windows: двойной клик по этому файлу.
rem При первом запуске создаётся папка venv и ставятся библиотеки из requirements.txt.

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if exist "venv\Scripts\python.exe" goto install
echo Первый запуск: создаю окружение Python...
%PY% -m venv venv
if errorlevel 1 goto nopython

:install
echo Проверяю библиотеки...
"venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto nopip

"venv\Scripts\python.exe" main.py
goto end

:nopython
echo.
echo Не найден Python. Установите Python 3.10 или новее с сайта python.org
echo и при установке поставьте галочку "Add python.exe to PATH".
goto end

:nopip
echo.
echo Не получилось установить библиотеки. Проверьте интернет и запустите run.bat ещё раз.

:end
echo.
pause
