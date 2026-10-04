"""Scoping search to a folder or a collection: by name, relative or absolute path, in the query text, for agents."""
import shutil

import pytest

from metachlorian.auth import LOCAL_ADMIN
from metachlorian.ingest.scan import add_source, scan_source
from metachlorian.search.engine import SearchEngine, SearchRequest
from metachlorian.service import Library

from .conftest import make_video
from .test_ingest_pipeline import run_all


@pytest.fixture()
def holiday_lib(lib, tmp_path, sample_video):
    """Videos/Holidays/Disney 2026/{a,b}.mp4, Videos/Work/c.mp4, and a duplicate of a.mp4 in Videos/Best."""
    s, db = lib
    root = tmp_path / "Videos"
    disney, work, best = root / "Holidays" / "Disney 2026", root / "Work", root / "Best"
    for d in (disney, work, best):
        d.mkdir(parents=True)
    shutil.copy(sample_video, disney / "a.mp4")
    make_video(disney / "b.mp4", segments=("smptehdbars", "testsrc"), seg_s=1.5)
    make_video(work / "c.mp4", segments=("rgbtestsrc", "smptebars"), seg_s=1.5)
    shutil.copy(sample_video, best / "a_copy.mp4")  # same content: one file found in two folders
    scan_source(db, add_source(db, str(root)))
    run_all(s, db)
    return s, db, root


def _files(res, key="filename"):
    # a.mp4 and Best/a_copy.mp4 are one file (same content); its primary name is whichever was found first.
    return {r[key].replace("a_copy", "a") for r in (res["results"] if "results" in res else res["assets"])}


def test_folder_scope_by_name_path_and_query_text(holiday_lib):
    s, db, root = holiday_lib
    eng = SearchEngine(db, s)

    def search(q="", **f):
        return eng.search(SearchRequest(q=q, filters=f, limit=100, hide_blocked=False))

    assert _files(search(folder="Disney 2026")) == {"a.mp4", "b.mp4"}
    assert _files(search(folder="Holidays/Disney 2026")) == {"a.mp4", "b.mp4"}
    assert _files(search(folder="holidays")) == {"a.mp4", "b.mp4"}          # parent folder includes subfolders
    assert _files(search(folder=str(root / "Work"))) == {"c.mp4"}             # absolute path
    assert _files(search(folder=["Work", "Disney 2026"])) == {"a.mp4", "b.mp4", "c.mp4"}
    assert _files(search(folder="Best")) == {"a.mp4"}                         # the duplicate belongs to both folders
    assert _files(search('folder:"Disney 2026"')) == {"a.mp4", "b.mp4"}      # written in the query
    assert _files(search("Folder: Work")) == {"c.mp4"}
    assert not _files(search(folder="Disn"))                                 # whole folder names only
    miss = search(folder="Disney 2025")
    assert miss["total"] == 0 and "Disney 2026" in miss["notes"][0]          # says so, and suggests the closest
    hits = [r for r in search(folder="Disney 2026")["results"] if r["filename"] == "b.mp4"]  # b is unique, so its folder is certain
    assert hits[0]["folder"] == str(root / "Holidays" / "Disney 2026")


def test_collection_scope_and_agent_tools(holiday_lib):
    s, db, root = holiday_lib
    lib = Library(db, s)
    eng = SearchEngine(db, s)
    c_shots = [r["uid"] for r in db.q("SELECT s.uid FROM shots s JOIN assets a ON a.id=s.asset_id WHERE a.filename='c.mp4' AND s.active=1")]
    b_shot = db.q1("SELECT s.uid FROM shots s JOIN assets a ON a.id=s.asset_id WHERE a.filename='b.mp4' AND s.active=1")["uid"]
    col = lib.create_collection(LOCAL_ADMIN, "Kids on rides")
    lib.add_to_collection(LOCAL_ADMIN, col["uid"], [c_shots[0], b_shot])

    for ref in (col["uid"], "kids on rides"):
        res = eng.search(SearchRequest(filters={"collection": ref}, limit=50, hide_blocked=False))
        assert {r["uid"] for r in res["results"]} == {c_shots[0], b_shot}
    both = eng.search(SearchRequest(q='collection:"Kids on rides"', filters={"folder": "Disney 2026"}, limit=50, hide_blocked=False))
    assert {r["uid"] for r in both["results"]} == {b_shot}                   # folder AND collection
    assert eng.search(SearchRequest(filters={"collection": "nope"}, hide_blocked=False))["notes"] == ['No collection called "nope".']

    folders = {f["relative"]: f for f in lib.folders(LOCAL_ADMIN)["folders"]}
    assert set(folders) == {"Videos", "Videos/Best", "Videos/Holidays", "Videos/Holidays/Disney 2026", "Videos/Work"}
    assert folders["Videos"]["files"] == 3 and folders["Videos/Holidays/Disney 2026"]["files"] == 2
    assert folders["Videos/Holidays"]["subfolders"] == 1 and folders["Videos/Holidays/Disney 2026"]["hours"] > 0
    assert [f["relative"] for f in lib.folders(LOCAL_ADMIN, q="disney")["folders"]] == ["Videos/Holidays/Disney 2026"]
    assert {f["name"] for f in lib.folders(LOCAL_ADMIN, parent=str(root))["folders"]} == {"Best", "Holidays", "Work"}

    files = lib.list_assets(LOCAL_ADMIN, folder="Disney 2026")
    assert _files(files) == {"a.mp4", "b.mp4"} and files["total"] == 2
    assert _files(lib.list_assets(LOCAL_ADMIN, collection="Kids on rides")) == {"b.mp4", "c.mp4"}
    assert folders["Videos/Holidays/Disney 2026"]["edit_types"] and sum(folders["Videos"]["edit_types"].values()) == 3
    assert lib.get_shot(LOCAL_ADMIN, db.q1("SELECT s.uid FROM shots s JOIN assets a ON a.id=s.asset_id WHERE a.filename='a_copy.mp4'"
                                           " OR a.filename='a.mp4' LIMIT 1")["uid"])["folders"] == [str(root / "Best"), str(root / "Holidays" / "Disney 2026")]
    near = SearchEngine(db, s).search(SearchRequest(filters={"collection": "kids on ride"}, hide_blocked=False))
    assert near["notes"] == ['No collection called "kids on ride". Closest: Kids on rides.'] and near["query"]["filters"]["collection"] == ["kids on ride"]
