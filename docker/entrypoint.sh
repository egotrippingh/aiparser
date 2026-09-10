#!/bin/sh
# Виртуальный рабочий стол для Camoufox и доступ к нему из браузера хоста.
#
# Camoufox работает с видимым окном (headless антиботы ловят чаще), а у
# контейнера нет экрана. Xvfb даёт виртуальный экран, fluxbox — рамки окон
# (без оконного менеджера окно входа нечем закрыть), x11vnc + noVNC
# показывают этот экран на http://localhost:6080 — там логинятся в сервисы
# и решают капчу.
set -e

rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/dev/null 2>&1 &

i=0
while [ ! -e /tmp/.X11-unix/X99 ]; do
    i=$((i + 1))
    if [ "$i" -gt 50 ]; then
        echo "Xvfb не поднялся за 10 секунд" >&2
        exit 1
    fi
    sleep 0.2
done

fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -forever -shared -nopw -quiet -localhost -rfbport 5900 >/dev/null 2>&1 &
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

# Firefox под Linux помечает занятый профиль симлинком `lock` с именем хоста
# и PID. Если контейнер убили посреди скана, симлинк остаётся и следующий
# запуск считает профиль занятым. Под Windows такого файла не бывает, так что
# удаляем только его — это артефакт исключительно контейнера.
if [ -d /app/data/profiles ]; then
    find /app/data/profiles -maxdepth 2 -name lock -type l -delete 2>/dev/null || true
fi

exec python -m app.main
