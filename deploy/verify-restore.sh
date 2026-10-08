#!/bin/sh
set -eu

cd "$(dirname "$0")"
archive=${1:?Usage: verify-restore.sh path/to/backup.dump}
test -s "$archive"

# Restore into a disposable database. The live aiparser database is never a target.
database="aiparser_restore_$(date -u +%Y%m%d%H%M%S)_$$"
docker compose exec -T db sh -eu -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  database=$1
  createdb -h 127.0.0.1 -U aiparser "$database"
  trap '\''dropdb -h 127.0.0.1 -U aiparser --if-exists --force "$database"'\'' EXIT
  pg_restore -h 127.0.0.1 -U aiparser -d "$database" --exit-on-error --no-owner --no-acl
  psql -h 127.0.0.1 -U aiparser -d "$database" -v ON_ERROR_STOP=1 -Atc \
    "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM wallets), (SELECT count(*) FROM alembic_version)" >/dev/null
' sh "$database" < "$archive"
echo "Restored archive successfully into isolated database."
