# Диагностика ответов

Агент 2026.9.29.6 передаёт сохранённую причину ошибки вместе с результатом. Отчёт показывает её отдельно от отсутствующего текста и даёт безопасную подсказку: войти в сервис при требовании авторизации либо запустить следующую полную проверку. Обычные ошибки запросов не перезапускаются автоматически и выборочного повтора нет.

Для старых результатов причина может отсутствовать: интерфейс честно сообщает, что её не передала прежняя версия агента. Источники показываются отдельным списком ссылок; текст ответа рендерится как обычный текст без HTML. Номерные ссылки внутри ответа не сопоставляются с источниками по догадке.

Историческое дополнение причины допускается только для уже принятого результата того же пользователя, устройства, локального ID, проекта, запуска, запроса, сервиса и статуса; заполненное поле не меняется. Нет проверки реальных провайдеров или повторных сканов.

Историческая отправка проходит по отдельному курсору пользователя/устройства: одна страница за heartbeat, только ошибочные статусы и уже синхронизированные строки. Курсор продвигается после ACK diagnostics_version=1. При сетевой ошибке или старом сервере повторяется позже.

WEB-PM: предоставленный пользователем HTML подтвердил уведомление «Вы достигли лимита бесплатных поисков», а не изменение селектора. Новая версия распознаёт видимый заголовок лимита как limit_reached и использует существующую остановку после трёх ограничений подряд. Вложенные номера цитат не сопоставляются с источниками, старые отсутствующие ответы не восстанавливаются.

## Publication gate

The existing root-owned release entry point rejects schema changes before stopping the app. Do not bypass it or rerun against a pre-migrated database with an incompatible rollback image. Prepare a compatibility image from the exact live image adding only this nullable model field and migration. Prove on an isolated verified PostgreSQL restore: pre/post migration core rows and wallet/ledger/check fingerprints agree; compatibility -> new -> compatibility preserves a synthetic diagnosis; compatibility -> downgrade -> previous starts before new diagnostics are accepted. Take a fresh verified backup before promotion. First promote compatibility, then ordinary CI deploy; CI rollback now targets the compatible previous image. Do not restore an older whole database over newer writes or downgrade after diagnoses arrive.

An active scan can stop when its settlement encounters a transport outage, so graceful shutdown alone does not prove uninterrupted scans. Complete packaging and clone validation before selecting an idle deployment window. Live provider scans, logins and payments are excluded from verification.
