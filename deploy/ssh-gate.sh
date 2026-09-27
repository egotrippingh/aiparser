#!/bin/bash
# Forced SSH command for the dedicated CI user. No shell, forwarding or arbitrary paths.
set -euo pipefail
request=${SSH_ORIGINAL_COMMAND:-}
if [[ "$request" =~ ^upload\ ([a-f0-9]{40})\ ([a-f0-9]{64})$ ]]; then
    revision=${BASH_REMATCH[1]}
    checksum=${BASH_REMATCH[2]}
    umask 077
    temporary=$(mktemp /var/lib/airate-ci/incoming/.upload-XXXXXX)
    trap 'rm -f -- "$temporary"' EXIT
    head -c 536870913 > "$temporary"
    test "$(stat -c %s "$temporary")" -le 536870912
    printf '%s  %s\n' "$checksum" "$temporary" | sha256sum -c - >/dev/null
    mv -- "$temporary" "/var/lib/airate-ci/incoming/$revision.tar.gz"
    printf 'Uploaded and verified %s\n' "$revision"
elif [[ "$request" =~ ^deploy\ ([a-f0-9]{40})\ ([a-f0-9]{64})$ ]]; then
    exec sudo /usr/local/sbin/airate-release "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
else
    printf 'Only verified upload/deploy commands are allowed.\n' >&2
    exit 64
fi
