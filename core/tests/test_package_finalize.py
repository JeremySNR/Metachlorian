"""Only the final atomic publish retries short Windows sharing/access failures."""
import pytest

from metachlorian.exports import package


def _locked(code):
    error = PermissionError('temporary directory lock')
    error.winerror = code
    return error


@pytest.mark.parametrize('code', [5, 32, 33])
def test_transient_windows_lock_retries_then_publishes(tmp_path, monkeypatch, code):
    staging, final = tmp_path / '.staged', tmp_path / 'published'
    staging.mkdir()
    (staging / 'manifest.json').write_text('{"complete":true}')
    rename, calls, waits = package.os.rename, [], []

    def flaky(source, destination):
        calls.append((source, destination))
        if len(calls) <= 2:
            raise _locked(code)
        return rename(source, destination)

    monkeypatch.setattr(package.os, 'rename', flaky)
    monkeypatch.setattr(package.time, 'sleep', waits.append)
    package._finalize_package(staging, final)
    assert len(calls) == 3 and waits == [0.1, 0.2]
    assert not staging.exists()
    assert (final / 'manifest.json').read_text() == '{"complete":true}'


def test_persistent_windows_lock_is_bounded_and_preserves_staging(tmp_path, monkeypatch):
    staging, final = tmp_path / '.staged', tmp_path / 'published'
    staging.mkdir()
    calls, waits = [], []

    def locked(*args):
        calls.append(args)
        raise _locked(5)

    monkeypatch.setattr(package.os, 'rename', locked)
    monkeypatch.setattr(package.time, 'sleep', waits.append)
    with pytest.raises(PermissionError):
        package._finalize_package(staging, final)
    assert len(calls) == 6 and waits == [0.1, 0.2, 0.4, 0.8, 1.6]
    assert staging.exists() and not final.exists()


@pytest.mark.parametrize('error', [OSError('disk problem'), PermissionError('ordinary permission denial')])
def test_unrelated_errors_are_not_retried(tmp_path, monkeypatch, error):
    calls, waits = [], []

    def fail(*args):
        calls.append(args)
        raise error

    monkeypatch.setattr(package.os, 'rename', fail)
    monkeypatch.setattr(package.time, 'sleep', waits.append)
    with pytest.raises(type(error), match=str(error)):
        package._finalize_package(tmp_path / '.staged', tmp_path / 'published')
    assert len(calls) == 1 and waits == []


@pytest.mark.parametrize('created_during_retry', [False, True])
def test_existing_destination_is_never_replaced(tmp_path, monkeypatch, created_during_retry):
    staging, final = tmp_path / '.staged', tmp_path / 'published'
    staging.mkdir()
    calls, waits = [], []

    def create_destination():
        final.mkdir()
        (final / 'keep.txt').write_text('existing package')

    if not created_during_retry:
        create_destination()

    def collision(*args):
        calls.append(args)
        create_destination()
        raise _locked(32)

    monkeypatch.setattr(package.os, 'rename', collision)
    monkeypatch.setattr(package.time, 'sleep', waits.append)
    with pytest.raises(FileExistsError):
        package._finalize_package(staging, final)
    assert len(calls) == int(created_during_retry)
    assert (final / 'keep.txt').read_text() == 'existing package' and staging.exists()
