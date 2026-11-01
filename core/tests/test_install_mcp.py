import json
import pytest
import tomlkit
from metachlorian.install_mcp import install

URL = 'http://127.0.0.1:8765/mcp'
TOKEN = 'mc_test_secret'

@pytest.mark.parametrize('client', ['codex', 'claude-code'])
def test_install_preserves_other_settings_and_is_repeatable(tmp_path, monkeypatch, client):
    monkeypatch.delenv('CODEX_HOME', raising=False)
    target = tmp_path / ('.codex/config.toml' if client == 'codex' else '.claude.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    original = '# keep this comment\nmodel = "example"\n[mcp_servers.other]\ncommand = "other"\n' if client == 'codex' else json.dumps({'theme': 'dark', 'mcpServers': {'other': {'command': 'other'}}})
    target.write_text(original)
    assert install(client, URL, TOKEN, home=tmp_path) == target
    first = target.read_text()
    assert 'other' in first
    assert TOKEN in first
    backups = list(target.parent.glob(target.name + '.backup-*'))
    assert len(backups) == 1 and backups[0].read_text() == original
    install(client, URL, TOKEN, home=tmp_path)
    assert target.read_text() == first
    assert len(list(target.parent.glob(target.name + '.backup-*'))) == 1
    install(client, URL, 'mc_new_secret', home=tmp_path)
    assert TOKEN not in target.read_text()
    if client == 'codex':
        assert '# keep this comment' in target.read_text()
        assert tomlkit.parse(target.read_text())['model'] == 'example'

@pytest.mark.parametrize('client', ['codex', 'claude-code'])
def test_malformed_configuration_is_untouched(tmp_path, monkeypatch, client):
    monkeypatch.delenv('CODEX_HOME', raising=False)
    target = tmp_path / ('.codex/config.toml' if client == 'codex' else '.claude.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('broken [[[ !')
    with pytest.raises(Exception):
        install(client, URL, TOKEN, home=tmp_path)
    assert target.read_text() == 'broken [[[ !'


def test_codex_home_and_local_only(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'custom'))
    assert install('codex', URL, TOKEN, home=tmp_path) == tmp_path / 'custom/config.toml'
    with pytest.raises(ValueError):
        install('codex', 'https://example.com/mcp', TOKEN, home=tmp_path)
