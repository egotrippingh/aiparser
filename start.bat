@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title AI Mentions Tracker

rem Запуск в один клик. Первый раз сам готовит всё нужное: окружение Python,
rem зависимости и браузер Camoufox. Дальше просто запускает программу и
rem открывает интерфейс в браузере. Камуфокс открывается на этом же ПК
rem обычными окнами, как и раньше.
rem
rem   start.bat           подготовить, если нужно, и запустить
rem   start.bat --setup   только подготовить, без запуска

rem Программа уже запущена - просто открываем интерфейс ещё раз.
netstat -ano | findstr /r /c:":8756 .*LISTENING" >nul
if errorlevel 1 goto setup
echo Программа уже запущена, открываю интерфейс.
start "" http://127.0.0.1:8756/
exit /b 0

:setup
rem Прокси нужен только установке: pip и загрузка браузера не понимают
rem системный прокси Windows. Самой программе его не выставляем, чтобы
rem браузер работал ровно так же, как при обычном запуске.
setlocal
if not defined HTTPS_PROXY call :system_proxy

if exist ".venv\Scripts\python.exe" goto deps
call :find_python
if not defined PY goto no_python
echo Создаю окружение Python в папке .venv ...
%PY% -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed

:deps
rem Зависимости ставим заново, только если requirements.txt изменился.
fc /b requirements.txt ".venv\requirements.installed" >nul 2>nul
if not errorlevel 1 goto browser
echo Устанавливаю зависимости ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
copy /y requirements.txt ".venv\requirements.installed" >nul

:browser
".venv\Scripts\python.exe" -c "from camoufox.pkgman import camoufox_path; camoufox_path(download_if_missing=False)" >nul 2>nul
if not errorlevel 1 goto ready
echo Скачиваю браузер Camoufox, это около 250 МБ, один раз ...
".venv\Scripts\python.exe" -m camoufox fetch
if errorlevel 1 goto failed

:ready
endlocal
if /i "%~1"=="--setup" (
    echo Всё готово. Для запуска дважды кликните start.bat
    exit /b 0
)

echo.
echo Запускаю. Интерфейс откроется в браузере: http://127.0.0.1:8756/
echo Не закрывайте это окно, пока работаете: закрыли - программа остановилась.
echo.
".venv\Scripts\python.exe" -m app.main --browser
if errorlevel 1 pause
exit /b 0

:find_python
set "PY="
py -3.10 -c "" >nul 2>nul && set "PY=py -3.10" && exit /b 0
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=py -3" && exit /b 0
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=python" && exit /b 0
exit /b 0

:system_proxy
rem Системный прокси из настроек Windows. Только простая форма адреса
rem вида host:port; если прокси задан по протоколам, пропускаем.
set "REGKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
set "PENABLE="
set "PSERVER="
for /f "tokens=3" %%a in ('reg query "%REGKEY%" /v ProxyEnable 2^>nul ^| findstr ProxyEnable') do set "PENABLE=%%a"
if not "%PENABLE%"=="0x1" exit /b 0
for /f "tokens=3" %%a in ('reg query "%REGKEY%" /v ProxyServer 2^>nul ^| findstr ProxyServer') do set "PSERVER=%%a"
if not defined PSERVER exit /b 0
echo %PSERVER%| findstr "=" >nul && exit /b 0
set "HTTP_PROXY=http://%PSERVER%"
set "HTTPS_PROXY=http://%PSERVER%"
echo Установка идёт через системный прокси %PSERVER%
exit /b 0

:no_python
echo.
echo Не найден Python 3.10 или новее.
echo Установите его с https://www.python.org/downloads/ - при установке
echo отметьте галочку "Add python.exe to PATH" - и запустите start.bat снова.
pause
exit /b 1

:failed
echo.
echo Подготовка не удалась - текст ошибки выше. Проверьте интернет и VPN
echo и запустите start.bat ещё раз: сделанное повторно не качается.
pause
exit /b 1
