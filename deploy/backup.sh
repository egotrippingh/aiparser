#!/bin/sh
set -eu

cd "$(dirname "$0")"
umask 077
exec 8>/run/airate-backup.lock
flock -w 300 8
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary="backups/.aiparser-$stamp-$$.dump"
archive="backups/aiparser-$stamp-$$.dump"
trap 'rm -f "$temporary"' EXIT HUP INT TERM

docker compose exec -T db sh -eu -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  exec pg_dump -h 127.0.0.1 -U aiparser -d aiparser -Fc --no-owner --no-acl
' > "$temporary"
test -s "$temporary"
sh ./verify-restore.sh "$temporary"
mv "$temporary" "$archive"
sha256sum "$archive" > "$archive.sha256"
echo "Backup saved: $archive"

# Off-host copy uses a separate private bucket and service account when configured.
# Prefer .env (mode 0600 on the VPS) over grepping rendered Compose JSON.
bucket=""
if test -f .env; then
  bucket=$(sed -n 's/^BACKUP_S3_BUCKET=//p' .env | tr -d '\r' | tail -n 1)
fi
case "$bucket" in
  ""|\"\"|\'\')
    echo "BACKUP_S3_BUCKET is empty; backup exists only on this VPS."
    ;;
  *)
    test -n "$(sed -n 's/^BACKUP_ACCESS_KEY_ID=//p' .env | tr -d '\r' | tail -n 1)"
    test -n "$(sed -n 's/^BACKUP_SECRET_ACCESS_KEY=//p' .env | tr -d '\r' | tail -n 1)"
    docker compose --profile ops run --rm -T --no-deps backup-upload "/backups/$(basename "$archive")"
    echo "Backup copied to the private off-host bucket."
    ;;
esac

# Keep the newest 30 verified dumps; never prune before a successful backup.
python3 - <<'PY'
from pathlib import Path
archives = sorted(Path('backups').glob('aiparser-*.dump'), key=lambda p: p.stat().st_mtime, reverse=True)
for archive in archives[30:]:
    archive.unlink()
    archive.with_suffix('.dump.sha256').unlink(missing_ok=True)
PY
