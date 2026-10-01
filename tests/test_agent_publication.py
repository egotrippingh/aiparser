import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('publish_agent', Path(__file__).resolve().parents[1] / 'scripts/publish-agent.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def release_files(directory):
    (directory / publisher.FILES['installer']).write_bytes(b'test installer')
    with zipfile.ZipFile(directory / publisher.FILES['portable'], 'w') as archive:
        archive.writestr('agent-version.txt', '2026.9.29.2')
        archive.writestr('account-url.txt', 'https://airate.tech')
    release = {'version': '2026.9.29.2'}
    for kind, name in publisher.FILES.items():
        contents = (directory / name).read_bytes()
        release[kind] = {'size_bytes': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
    (directory / 'agent-release.json').write_text(json.dumps(release), encoding='utf-8')
    return release


def test_publication_rejects_changed_artifact(tmp_path):
    expected = release_files(tmp_path)
    assert publisher.validate_release(tmp_path) == expected
    (tmp_path / publisher.FILES['installer']).write_bytes(b'other contents')
    with pytest.raises(ValueError, match='does not match'):
        publisher.validate_release(tmp_path)


def test_public_verification_rejects_wrong_metadata_and_download(tmp_path, monkeypatch):
    release = release_files(tmp_path)

    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size=-1):
            if size < 0: return self.body
            result, self.body = self.body[:size], self.body[size:]
            return result

    def wrong_metadata(url, timeout):
        return Response(json.dumps({'available': True}).encode())
    monkeypatch.setattr(publisher.urllib.request, 'urlopen', wrong_metadata)
    with pytest.raises(ValueError, match='metadata'):
        publisher.verify_public(release)

    metadata = {'available': True, 'url': '/downloads/AIRate-Setup.exe',
                'size_bytes': release['installer']['size_bytes'], 'release': release}
    calls = iter([Response(json.dumps(metadata).encode()), Response(b'wrong'), Response(b'wrong')])
    monkeypatch.setattr(publisher.urllib.request, 'urlopen', lambda url, timeout: next(calls))
    with pytest.raises(ValueError, match='installer download'):
        publisher.verify_public(release)

    contents = {kind: (tmp_path / name).read_bytes() for kind, name in publisher.FILES.items()}
    calls = iter([Response(json.dumps(metadata).encode()), Response(contents['installer']), Response(b'wrong')])
    monkeypatch.setattr(publisher.urllib.request, 'urlopen', lambda url, timeout: next(calls))
    with pytest.raises(ValueError, match='portable download'):
        publisher.verify_public(release)

    calls = iter([Response(json.dumps(metadata).encode()), Response(contents['installer']), Response(contents['portable'])])
    monkeypatch.setattr(publisher.urllib.request, 'urlopen', lambda url, timeout: next(calls))
    publisher.verify_public(release)


def test_main_passes_pinned_known_hosts_to_every_ssh_call(tmp_path, monkeypatch):
    release_files(tmp_path)
    calls = []
    monkeypatch.setattr(sys, 'argv', ['publish-agent.py', '--host', 'publisher@example.test', '--key', 'key',
                                     '--known-hosts', 'hosts', '--dist', str(tmp_path)])
    monkeypatch.setattr(publisher.subprocess, 'run', lambda command, **kwargs: calls.append(command))
    publisher.main()
    assert len(calls) == 3
    assert all(command[command.index('publisher@example.test') - 2:command.index('publisher@example.test') + 1]
               == ['-o', 'UserKnownHostsFile=hosts', 'publisher@example.test'] for command in calls)


@pytest.mark.parametrize('name,value', [('agent-version.txt', '0.1.0'), ('account-url.txt', 'https://example.test'), ('data/account.db', 'private'), ('.env', 'private')])
def test_publication_rejects_wrong_build_and_private_data(tmp_path, name, value):
    release = release_files(tmp_path)
    archive_path = tmp_path / publisher.FILES['portable']
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('agent-version.txt', value if name == 'agent-version.txt' else release['version'])
        archive.writestr('account-url.txt', value if name == 'account-url.txt' else 'https://airate.tech')
        if name not in ('agent-version.txt', 'account-url.txt'):
            archive.writestr(name, value)
    contents = archive_path.read_bytes()
    release['portable'] = {'size_bytes': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
    (tmp_path / 'agent-release.json').write_text(json.dumps(release), encoding='utf-8')
    with pytest.raises(ValueError):
        publisher.validate_release(tmp_path)


def stage_release(directory, version, stage):
    release = {'version': version}
    for kind, name in publisher.FILES.items():
        contents = (kind + version).encode()
        (directory / (name + '.' + stage + '.upload')).write_bytes(contents)
        release[kind] = {'size_bytes': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
    return release


@pytest.mark.skipif(os.name != 'posix', reason='Production activation uses Linux flock and symlinks')
def test_interrupted_activation_preserves_complete_old_release_and_retry(tmp_path, monkeypatch):
    old = stage_release(tmp_path, '2026.9.29.2', 'old')
    publisher.activate(tmp_path, 'old', old)
    new = stage_release(tmp_path, '2026.9.29.3', 'new')
    original = os.replace
    def fail_pointer(source, target):
        if Path(target).name == 'agent-current':
            raise OSError('Interrupted before the atomic switch')
        return original(source, target)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail_pointer)
        with pytest.raises(OSError):
            publisher.activate(tmp_path, 'new', new)
    assert json.loads((tmp_path / 'agent-release.json').read_text()) == old
    for kind, name in publisher.FILES.items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == old[kind]['sha256']
    new = stage_release(tmp_path, '2026.9.29.3', 'retry')
    publisher.activate(tmp_path, 'retry', new)
    assert json.loads((tmp_path / 'agent-release.json').read_text()) == new
    assert json.loads((tmp_path / 'agent-previous/agent-release.json').read_text()) == old
    downgrade = stage_release(tmp_path, '2026.9.29.2', 'downgrade')
    with pytest.raises(AssertionError, match='downgrade'):
        publisher.activate(tmp_path, 'downgrade', downgrade)
    rebuilt = stage_release(tmp_path, '2026.9.29.3', 'rebuilt')
    rebuilt_path = tmp_path / (publisher.FILES['installer'] + '.rebuilt.upload')
    rebuilt_path.write_bytes(b'rebuilt artifact')
    rebuilt['installer'] = {'size_bytes': rebuilt_path.stat().st_size,
                            'sha256': hashlib.sha256(rebuilt_path.read_bytes()).hexdigest()}
    with pytest.raises(AssertionError, match='immutable'):
        publisher.activate(tmp_path, 'rebuilt', rebuilt)


@pytest.mark.skipif(os.name != 'posix', reason='Production activation uses Linux flock and symlinks')
def test_concurrent_activation_keeps_latest_complete(tmp_path):
    import subprocess
    import sys
    old = stage_release(tmp_path, '2026.9.29.2', 'initial')
    publisher.activate(tmp_path, 'initial', old)
    candidates = [(stage, stage_release(tmp_path, version, stage)) for stage, version in
                  [('first', '2026.9.29.3'), ('second', '2026.9.29.4')]]
    processes = []
    for stage, release in candidates:
        command = f'import importlib.util,json;from pathlib import Path;s=importlib.util.spec_from_file_location("p",{str(spec.origin)!r});p=importlib.util.module_from_spec(s);s.loader.exec_module(p);p.activate(Path({str(tmp_path)!r}),{stage!r},json.loads({json.dumps(release)!r}))'
        processes.append(subprocess.Popen([sys.executable, '-c', command], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    outcomes = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
    assert outcomes[1][2] == 0, outcomes
    assert outcomes[0][2] in (0, 1), outcomes  # Earlier release may be refused after .4 wins.
    latest = json.loads((tmp_path / 'agent-release.json').read_text())
    assert latest['version'] == '2026.9.29.4'
    for kind, name in publisher.FILES.items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == latest[kind]['sha256']
