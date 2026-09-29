"""Publish verified Windows artifacts, then announce the release. Requires OpenSSH."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import re
import shlex
import subprocess
import uuid
import zipfile

FILES = {'installer': 'AIRate-Setup-latest.exe', 'portable': 'AI-Mentions-Windows-latest.zip'}


def activate(directory: Path, staged_id: str, release: dict) -> None:
    """Linux: serialize activation and atomically switch a complete release directory."""
    import fcntl
    import os
    import shutil

    files = {'installer': 'AIRate-Setup-latest.exe', 'portable': 'AI-Mentions-Windows-latest.zip'}
    with (directory / '.agent-publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for kind, name in files.items():
            staged = directory / (name + '.' + staged_id + '.upload')
            with staged.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == release[kind]['sha256'], 'Staged checksum changed'
            assert staged.stat().st_size == release[kind]['size_bytes']
        releases = directory / 'agent-releases'
        releases.mkdir(exist_ok=True)
        current = directory / 'agent-current'
        if not current.is_symlink():
            assert not current.exists(), 'agent-current must be a symlink'
            legacy = releases / ('legacy-' + staged_id)
            legacy.mkdir(exist_ok=True)
            for name in (*files.values(), 'agent-release.json'):
                source = directory / name
                if source.exists():
                    shutil.copy2(source, legacy / name)
            current.symlink_to('agent-releases/' + legacy.name, target_is_directory=True)
        # Bootstrap fixed download aliases once, retaining the complete old directory.
        for name in (*files.values(), 'agent-release.json'):
            alias = directory / name
            if not alias.is_symlink():
                temporary = directory / ('.alias-' + staged_id + '-' + name)
                temporary.symlink_to('agent-current/' + name)
                os.replace(temporary, alias)
        manifest = current / 'agent-release.json'
        old = json.loads(manifest.read_text()) if manifest.exists() else None
        if old:
            assert tuple(map(int, release['version'].split('.'))) >= tuple(map(int, old['version'].split('.'))), 'Refusing downgrade'
            assert old['version'] != release['version'] or old == release, 'A published version is immutable; bump the version'
        target = releases / release['version']
        if target.exists():
            assert json.loads((target / 'agent-release.json').read_text()) == release, 'A published version is immutable'
            for kind, name in files.items():
                with (target / name).open('rb') as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == release[kind]['sha256']
            for name in files.values():
                (directory / (name + '.' + staged_id + '.upload')).unlink()
        else:
            stage = releases / ('.stage-' + staged_id)
            stage.mkdir(exist_ok=True)
            for name in files.values():
                uploaded = directory / (name + '.' + staged_id + '.upload')
                os.chmod(uploaded, 0o644)
                os.replace(uploaded, stage / name)
            (stage / 'agent-release.json').write_text(json.dumps(release), encoding='utf-8')
            os.rename(stage, target)
        destination = 'agent-releases/' + target.name
        # ponytail: retain release directories for rollback; prune older ones when disk space requires it.
        if os.readlink(current) != destination:
            previous = directory / ('.previous-' + staged_id)
            previous.symlink_to(os.readlink(current), target_is_directory=True)
            os.replace(previous, directory / 'agent-previous')
            pointer = directory / ('.current-' + staged_id)
            pointer.symlink_to(destination, target_is_directory=True)
            os.replace(pointer, current)
        print(json.dumps(release), flush=True)


def validate_release(directory: Path) -> dict:
    release = json.loads((directory / 'agent-release.json').read_text(encoding='utf-8-sig'))
    if not isinstance(release, dict) or not re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){3}', str(release.get('version', ''))):
        raise ValueError('Invalid release version')
    for kind, name in FILES.items():
        artifact = directory / name
        record = release.get(kind)
        if not isinstance(record, dict) or type(record.get('size_bytes')) is not int or record['size_bytes'] <= 0:
            raise ValueError(f'Invalid {kind} size')
        if not re.fullmatch(r'[a-f0-9]{64}', str(record.get('sha256', ''))):
            raise ValueError(f'Invalid {kind} checksum')
        with artifact.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if artifact.stat().st_size != record['size_bytes'] or checksum != record['sha256']:
            raise ValueError(f'{kind} does not match release metadata')
    with zipfile.ZipFile(directory / FILES['portable']) as archive:
        if archive.read('agent-version.txt').decode('utf-8-sig').strip() != release['version']:
            raise ValueError('Portable version does not match release metadata')
        if archive.read('account-url.txt').decode('utf-8-sig').strip() != 'https://airate.tech':
            raise ValueError('Only the production agent can be published')
        if any(name.startswith('data/') or Path(name).name.startswith('.env') for name in archive.namelist()):
            raise ValueError('Portable archive contains user data or environment files')
    return release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='SSH user@host; existing known_hosts entry required')
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*', args.host):
        parser.error('--host must be user@host')
    release = validate_release(args.dist)
    staged_id = uuid.uuid4().hex
    ssh = ['ssh', '-i', str(args.key), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'ConnectTimeout=25', '-o', 'ServerAliveInterval=15', args.host]
    # Unique uploads avoid concurrent publishers overwriting each other's staging files.
    for kind, name in FILES.items():
        staged = f'{name}.{staged_id}.upload'
        command = f'''import hashlib, shutil, sys
from pathlib import Path
target = Path('/opt/airate/deploy/downloads') / {staged!r}
with target.open('wb') as output:
    shutil.copyfileobj(sys.stdin.buffer, output)
with target.open('rb') as source:
    assert hashlib.file_digest(source, 'sha256').hexdigest() == {release[kind]['sha256']!r}, 'Checksum mismatch'
assert target.stat().st_size == {release[kind]['size_bytes']!r}, 'Size mismatch'
print({kind!r} + ' staged and verified', flush=True)
'''
        with (args.dist / name).open('rb') as stream:
            subprocess.run(ssh + ['python3 -c ' + shlex.quote(command)], stdin=stream, check=True)
    command = f'''import hashlib, json
from pathlib import Path
{inspect.getsource(activate)}
activate(Path('/opt/airate/deploy/downloads'), {staged_id!r}, json.loads({json.dumps(release)!r}))
'''
    subprocess.run(ssh + ['python3 -c ' + shlex.quote(command)], check=True)


if __name__ == '__main__':
    main()
