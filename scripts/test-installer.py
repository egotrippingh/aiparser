"""Windows-only install/upgrade/uninstall smoke test; no existing install allowed.

Run from the repository root. Artifacts/logs stay under build. The test disables
shortcuts and auto-launch, isolates app data, and removes its installation.
"""

import argparse
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import winreg

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--installer', required=True, type=Path)
parser.add_argument('--bundle', required=True, type=Path)
parser.add_argument('--browser', required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
setup = args.installer.resolve(strict=True)
bundle = args.bundle.resolve(strict=True)
browser = args.browser.resolve(strict=True)
assert (bundle / 'AI-Mentions.exe').is_file()
(root / 'build').mkdir(exist_ok=True)
registry = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B60FD775-5E70-4C13-91EC-CB07D8539FE0}_is1'
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry):
        raise RuntimeError('An AIRate installation is already registered; do not overwrite it')
except FileNotFoundError:
    pass

temp = Path(tempfile.mkdtemp(prefix='installer-smoke-', dir=root / 'build'))
target = temp / 'AIRate тест папки'
user = temp / 'user'
user.mkdir()
env = dict(os.environ, LOCALAPPDATA=str(user))
flags = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/TASKS=', f'/DIR={target}']

def run(command, **kwargs):
    subprocess.run(command, check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW, **kwargs)

try:
    run([str(setup), *flags, f'/LOG={temp / "install.log"}'])
    assert (target / 'installed-mode.txt').is_file()
    assert (target / 'account-url.txt').read_text().strip() == 'https://airate.tech'
    assert not (target / 'data').exists()
    source_files = []
    for origin, destination in ((bundle, target), (browser, target / 'browser')):
        files = [p for p in origin.rglob('*') if p.is_file()]
        source_files.extend(files)
        for source in files:
            installed = destination / source.relative_to(origin)
            assert installed.is_file(), f'Installer omitted {source.relative_to(origin)}'
            with source.open('rb') as a, installed.open('rb') as b:
                assert hashlib.file_digest(a, 'sha256').digest() == hashlib.file_digest(b, 'sha256').digest()
    run([str(target / 'AI-Mentions.exe'), '--self-test', '--self-test-browser'], env=env)
    data = user / 'AIParser'
    assert (data / 'aiparser.db').is_file()
    assert str(target / 'browser' / 'camoufox.exe') in (data / 'agent.log').read_text(encoding='utf-8')
    sentinel = data / 'profile-preservation-probe.txt'
    sentinel.write_text('keep on upgrade and uninstall')
    run([str(setup), *flags, f'/LOG={temp / "upgrade.log"}'])
    run([str(target / 'AI-Mentions.exe'), '--self-test'], env=env)
    assert sentinel.read_text() == 'keep on upgrade and uninstall'
finally:
    uninstaller = target / 'unins000.exe'
    if uninstaller.exists():
        run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/LOG={temp / "uninstall.log"}'])

assert not (target / 'AI-Mentions.exe').exists()
assert sentinel.read_text() == 'keep on upgrade and uninstall'
assert (data / 'aiparser.db').is_file()
print(json.dumps({'install': True, 'installed_exe_self_test': True, 'upgrade': True,
                  'verified_files': len(source_files),
                  'uninstall_preserves_data': True, 'logs': str(temp)}, ensure_ascii=False))
