#!/bin/bash
# Root-owned deployment entry point. CI cannot edit this script or Compose configuration.
set -Eeuo pipefail
test "$(id -u)" = 0
revision=${1:-}
checksum=${2:-}
[[ "$revision" =~ ^[a-f0-9]{40}$ && "$checksum" =~ ^[a-f0-9]{64}$ ]]
exec 9>/run/airate-release.lock
flock -n 9 || { echo 'Another deployment is running'; exit 75; }
cd /opt/airate/deploy
incoming="/var/lib/airate-ci/incoming/$revision.tar.gz"
test -f "$incoming" && test ! -L "$incoming"
install -d -m 0700 /opt/airate/releases
archive="/opt/airate/releases/$revision.tar.gz"
install -m 0600 "$incoming" "$archive"
printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c -
docker load --input "$archive"
image="airate-web:$revision"
docker image inspect "$image" >/dev/null
actual_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
test "$actual_revision" = "$revision"
container=$(docker compose ps -q web)
test -n "$container"
previous_image=$(docker inspect --format '{{.Image}}' "$container")
previous_release=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^AIRATE_RELEASE=//p')
previous_release=${previous_release:-local}

# Schema-changing releases need a separately reviewed migration plan. Automatic
# rollback is safe only while the old and new application share the same schema.
database_head=$(docker compose exec -T db psql -U aiparser -d aiparser -Atc 'select version_num from alembic_version')
candidate_head=$(docker run --rm --entrypoint python "$image" -c 'from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config("/srv/alembic.ini")).get_current_head())')
test "$database_head" = "$candidate_head" || {
    echo 'Schema change detected. Deployment stopped before touching the running application.'
    exit 65
}
sh ./backup.sh

write_release() {
    python3 - "$1" "$2" <<'PY'
from pathlib import Path
import os,sys
path=Path('.env')
lines=[line for line in path.read_text().splitlines() if not line.startswith(('AIRATE_IMAGE=', 'AIRATE_RELEASE='))]
lines += ['AIRATE_IMAGE='+sys.argv[1], 'AIRATE_RELEASE='+sys.argv[2]]
temporary=path.with_name('.env.release-tmp')
temporary.write_text('\n'.join(lines)+'\n')
temporary.chmod(0o600)
os.replace(temporary,path)
PY
}
switched=0
rollback() {
    result=$?
    trap - ERR
    if test "$switched" = 1; then
        echo 'New application failed; restoring the previous image. Database is not restored or erased.'
        write_release "$previous_image" "$previous_release"
        if docker compose up -d --no-build --no-deps --wait --wait-timeout 120 web; then
            echo 'Previous application restored.'
        else
            echo 'Rollback failed; manual intervention is required.' >&2
        fi
    fi
    exit "$result"
}
trap rollback ERR
switched=1
# SIGTERM drains active Uvicorn requests for up to 150s; Docker waits 180s.
docker compose stop web
write_release "$image" "$revision"
docker compose up -d --no-build --no-deps --wait --wait-timeout 120 web
docker compose exec -T web python -c 'import json,os,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/ready",timeout=5)); assert d["release"] == os.environ["AIRATE_RELEASE"]'
curl -fsS --retry 3 --retry-delay 2 --max-time 15 --resolve airate.tech:443:127.0.0.1 https://airate.tech/ >/dev/null
printf '%s\n' "$revision" > /opt/airate/releases/current
printf 'Released %s\n' "$revision"
# Keep images available for rollback; remove only the verified transport archives.
rm -f -- "$archive" "$incoming"
# Retain the active and previous images plus the newest three release tags.
python3 - "$image" "$previous_image" <<'PY'
import json,subprocess,sys
tags=subprocess.check_output(['docker','image','ls','airate-web','--format','{{.Repository}}:{{.Tag}}'],text=True).splitlines()
tags=[t for t in tags if not t.endswith(':<none>')]
if tags:
    records=json.loads(subprocess.check_output(['docker','image','inspect',*tags],text=True))
    records.sort(key=lambda row:row['Created'],reverse=True)
    keep={row['Id'] for row in records[:3]}
    keep.add(sys.argv[2])
    for row in records:
        if row['Id'] not in keep:
            for tag in row.get('RepoTags') or []:
                if tag.startswith('airate-web:') and tag != sys.argv[1]:
                    subprocess.run(['docker','image','rm',tag],check=False)
PY
