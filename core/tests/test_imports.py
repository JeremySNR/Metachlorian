"""Imports from web links: a fake yt-dlp stands in for the network (the real binary is exercised by hand, see eval)."""
import json
import os
import sys
import textwrap
import time

import pytest

from metachlorian.auth import LOCAL_ADMIN
from metachlorian.ingest import importer, ytdlp
from metachlorian.service import Library

FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, shutil, sys
    args = sys.argv[1:]
    url = args[args.index("--") + 1] if "--" in args else ""
    log = os.environ["FAKE_YTDLP_LOG"]
    with open(log, "a") as f:
        f.write(json.dumps(args) + "\\n")
    def video(vid, title, extra=None):
        d = {{"id": vid, "title": title, "duration": 6, "webpage_url": "https://www.youtube.com/watch?v=" + vid,
             "extractor_key": "Youtube", "uploader": "Mickey Fan", "upload_date": "20260805"}}
        d.update(extra or {{}})
        return d
    if "private" in url:
        sys.stderr.write("ERROR: [youtube] priv: Private video. Sign in if you've been granted access to this video\\n")
        sys.exit(1)
    if "slow" in url and "-J" not in args:
        import time; time.sleep(30)
    if "-J" in args:
        if "list=" in url and "--yes-playlist" in args:
            print(json.dumps({{"_type": "playlist", "title": "Disney 2026", "extractor_key": "YoutubeTab", "entries": [
                {{"url": "https://www.youtube.com/watch?v=aaa", "title": "Castle", "id": "aaa", "ie_key": "Youtube", "duration": 6}},
                {{"url": "https://www.youtube.com/watch?v=bbb", "title": "Parade", "id": "bbb", "ie_key": "Youtube", "duration": 6}}]}}))
        else:
            vid = url.rsplit("=", 1)[-1]
            print(json.dumps(video(vid, "Video " + vid)))
        sys.exit(0)
    out = args[args.index("-o") + 1]
    vid = url.rsplit("=", 1)[-1]
    extra = {{"license": "Creative Commons Attribution license (reuse allowed)", "tags": ["fireworks", "castle"]}} if vid == "cc" else {{}}
    meta = video(vid, "Video " + vid, extra)
    path = out.replace("%(title).120B", meta["title"]).replace("%(id)s", vid).replace("%(ext)s", "mp4")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copy(os.environ["FAKE_YTDLP_VIDEO"], path)
    if vid != "same":
        with open(path, "ab") as f:  # each video its own bytes (trailing data is ignored by decoders)
            f.write(vid.encode() * 64)
    with open(path[:-4] + ".info.json", "w") as f:
        json.dump(meta, f)
    print("[download] 50.0% of 1MiB"); print("[download] 100% of 1MiB")
    print("MC_FILE:" + path)
''')


@pytest.fixture()
def fake(lib, tmp_path, sample_video, monkeypatch):
    s, db = lib
    exe = tmp_path / "yt-dlp"
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(0o755)
    monkeypatch.setenv("FAKE_YTDLP_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setenv("FAKE_YTDLP_VIDEO", str(sample_video))
    s.ytdlp_path = str(exe)
    (tmp_path / "calls.log").touch()
    return s, db, Library(db, s), tmp_path / "calls.log"


def _wait(db, ids, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        rows = db.q(f"SELECT * FROM imports WHERE id IN ({','.join('?' * len(ids))}) OR parent_id IN ({','.join('?' * len(ids))})", (*ids, *ids))
        if rows and all(r["status"] not in importer.ACTIVE for r in rows):
            return {r["id"]: dict(r) for r in rows}
        time.sleep(0.2)
    raise AssertionError("imports did not finish")


def test_import_single_video_lands_in_folder_with_origin_and_unknown_rights(fake):
    s, db, lib, log = fake
    res = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=cc"], folder="Holidays/Disney 2026")
    rows = _wait(db, [res["imports"][0]["id"]])
    r = next(iter(rows.values()))
    assert r["status"] == "done" and r["title"] == "Video cc" and r["uploader"] == "Mickey Fan"
    assert r["path"].endswith("imports/Holidays/Disney 2026/Video cc [cc].mp4") and os.path.exists(r["path"])
    assert not os.path.exists(r["path"][:-4] + ".info.json")
    assert time.gmtime(os.stat(r["path"]).st_mtime)[:3] == (2026, 8, 5)        # file dated by the upload date
    asset = lib.get_asset(LOCAL_ADMIN, db.q1("SELECT uid FROM assets WHERE id=?", (r["asset_id"],))["uid"])
    assert asset["origin"]["url"] == "https://www.youtube.com/watch?v=cc" and asset["origin"]["upload_date"] == "2026-08-05"
    rights = asset["rights"]
    assert rights["status"] == "unknown" and "Creative Commons" in rights["notes"] and rights["licence"].startswith("CC BY")
    assert rights["attribution"] == "Mickey Fan (YouTube)"
    assert lib.list_assets(LOCAL_ADMIN, folder="Disney 2026")["total"] == 1
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert all(c[c.index("--") + 1].startswith("https://") for c in calls)     # the link is never read as an option
    # The same video again is recognised, not downloaded twice.
    again = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=cc"])
    dup = next(iter(_wait(db, [again["imports"][0]["id"]]).values()))
    assert dup["status"] == "duplicate" and dup["asset_id"] == r["asset_id"]


def test_playlist_expands_into_one_import_per_video(fake):
    s, db, lib, _ = fake
    res = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/playlist?list=PL1"], playlist=True)
    pid = res["imports"][0]["id"]
    rows = _wait(db, [pid])
    parent = rows[pid]
    kids = [r for r in rows.values() if r["parent_id"] == pid]
    assert parent["status"] == "expanded" and parent["folder"] == "YouTube/Disney 2026" and "2 videos" in parent["message"]
    assert sorted(k["title"] for k in kids) == ["Video aaa", "Video bbb"] and all(k["status"] == "done" for k in kids)
    assert all("/imports/YouTube/Disney 2026/" in k["path"] for k in kids)
    assert len(lib.import_status(LOCAL_ADMIN, pid)["children"]) == 2


def test_failures_explain_the_next_step_and_can_be_retried_or_cancelled(fake):
    s, db, lib, _ = fake
    bad = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=private"])["imports"][0]["id"]
    r = _wait(db, [bad])[bad]
    assert r["status"] == "failed" and "Private video" in r["error"] and "cookies.txt" in r["error"]
    lib.import_action(LOCAL_ADMIN, bad, "retry")
    assert _wait(db, [bad])[bad]["status"] == "failed"
    slow = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=slow"])["imports"][0]["id"]
    end = time.time() + 20
    while db.q1("SELECT status FROM imports WHERE id=?", (slow,))["status"] != "downloading" and time.time() < end:
        time.sleep(0.1)
    lib.import_action(LOCAL_ADMIN, slow, "cancel")
    assert _wait(db, [slow], 15)[slow]["status"] == "cancelled"
    lib.import_action(LOCAL_ADMIN, slow, "forget")
    assert db.q1("SELECT 1 FROM imports WHERE id=?", (slow,)) is None


def test_links_folders_and_cookie_files_are_validated(fake, monkeypatch):
    s, db, lib, _ = fake
    for bad in ("file:///etc/passwd", "--exec=rm", "javascript:alert(1)", ""):
        with pytest.raises(ValueError):
            importer.enqueue(db, s, [bad])
    with pytest.raises(ValueError, match="max_height"):
        importer.enqueue(db, s, ["https://example.com/v.mp4"], max_height=999)
    assert importer.safe_folder("../../etc//passwd") == "etc/passwd"
    assert importer.safe_folder("/abs/Disney 2026") == "abs/Disney 2026"
    s.require_auth = True  # team mode: no fetching the server's own network
    with pytest.raises(ValueError, match="own network"):
        importer.check_url("http://127.0.0.1:8080/x.mp4", s)
    s.require_auth = False
    with pytest.raises(ValueError, match="cookies.txt"):
        lib.set_import_cookies(LOCAL_ADMIN, b"not a cookie file")
    st = lib.set_import_cookies(LOCAL_ADMIN, b"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n")
    assert st["cookies_file"] and oct(os.stat(ytdlp.cookies_file(s)).st_mode)[-3:] == "600"
    assert ytdlp.auth_args(s)[-2:] == ["--cookies", str(ytdlp.cookies_file(s))] and "secret" not in json.dumps(st)
    assert not lib.set_import_cookies(LOCAL_ADMIN, None)["cookies_file"]
    s.import_cookies_browser = "firefox"
    assert ytdlp.auth_args(s)[-2:] == ["--cookies-from-browser", "firefox"]
    assert "Sign in to the site in" not in ytdlp.login_hint("ERROR: Sign in to confirm", s)  # browser set: a different hint


def test_origin_outlives_the_import_list_and_duplicates_are_recognised(fake):
    s, db, lib, _ = fake
    first = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=keep"])["imports"][0]["id"]
    r = _wait(db, [first])[first]
    lib.import_action(LOCAL_ADMIN, first, "forget")
    uid = db.q1("SELECT uid FROM assets WHERE id=?", (r["asset_id"],))["uid"]
    assert lib.get_asset(LOCAL_ADMIN, uid)["origin"]["url"].endswith("v=keep")          # still known after removing the row
    again = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=keep"])["imports"][0]["id"]
    assert _wait(db, [again])[again]["status"] == "duplicate"                             # recognised from the file itself
    # Different link, same bytes as a file already in the library: one copy kept, reported as already there.
    a = lib.import_urls(LOCAL_ADMIN, ["https://www.youtube.com/watch?v=same"])["imports"][0]["id"]
    ra = _wait(db, [a])[a]
    b_link = "https://vimeo.com/watch?v=same"
    b = lib.import_urls(LOCAL_ADMIN, [b_link])["imports"][0]["id"]
    rb = _wait(db, [b])[b]
    assert ra["status"] == "done" and rb["status"] in ("duplicate",) and rb["asset_id"] == ra["asset_id"]
    assert len(list((s.data_dir / "imports").rglob("*same*"))) == 1


def test_error_text_is_cleaned_and_network_errors_get_no_login_advice():
    assert ytdlp.clean_error("ERROR: [youtube] abc: Unable to download webpage: HTTP Error 403: Forbidden; please report this issue on "
                             "https://github.com/yt-dlp/yt-dlp/issues , filling out the template. Confirm you are on the latest version "
                             "using  yt-dlp -U") == "Unable to download webpage: HTTP Error 403: Forbidden"
    assert not ytdlp.is_auth_error("Unable to connect to proxy: 403 Forbidden")
    assert ytdlp.is_auth_error("Private video. Sign in if you've been granted access")
