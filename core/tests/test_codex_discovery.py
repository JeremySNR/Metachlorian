import os

from metachlorian.llm import find_codex


def install(tmp_path, version):
    exe = tmp_path / 'OpenAI' / 'Codex' / 'bin' / version / 'codex.exe'
    exe.parent.mkdir(parents=True)
    exe.write_text('test executable')
    exe.chmod(0o755)
    return exe


def test_desktop_discovery_with_stale_worker_path(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr('metachlorian.llm.shutil.which', lambda _: None)
    old = install(tmp_path, 'old')
    current = install(tmp_path, 'current')
    os.utime(old, (10, 10))
    os.utime(current, (20, 20))
    assert find_codex() == str(current)
    old.unlink()
    assert find_codex(str(old)) == str(current)
    assert find_codex(str(old).replace('\\', '/')) == str(current)


def test_existing_explicit_path_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    old = install(tmp_path, 'pinned')
    install(tmp_path, 'current')
    assert find_codex(str(old)) == str(old)


def test_missing_custom_path_is_not_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    install(tmp_path, 'current')
    assert find_codex(str(tmp_path / 'custom' / 'codex.exe')) is None


def test_path_install_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    install(tmp_path, 'current')
    monkeypatch.setattr('metachlorian.llm.shutil.which', lambda _: '/usr/bin/codex')
    assert find_codex() == '/usr/bin/codex'


def test_no_desktop_install_and_no_path(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr('metachlorian.llm.shutil.which', lambda _: None)
    monkeypatch.setattr('metachlorian.llm.os.access', lambda *args: False)
    assert find_codex() is None
