"""The planner: what re-runs when an analyser, a setting, a model or the file changes, and nothing else."""
from __future__ import annotations

import pytest

from metachlorian import pipeline
from metachlorian.analysers import registry

from .conftest import run_all


def _descendants(name: str) -> set[str]:
    out: set[str] = set()
    todo = [name]
    while todo:
        n = todo.pop()
        for a in registry.topological():
            if n in a.requires and a.name not in out:
                out.add(a.name)
                todo.append(a.name)
    return out


def _chain_keys(settings, content_hash: str) -> dict[str, str]:
    """Every analyser's input key when each upstream analyser ran with its current key."""
    keys: dict[str, str] = {}
    for a in registry.topological():
        keys[a.name] = a.input_key(settings, content_hash, {d: keys[d] for d in a.requires})
    return keys


def _runs(db, aid) -> dict[str, tuple[str, float]]:
    return {r["analyser"]: (r["input_key"], r["started_at"]) for r in
            db.q("SELECT analyser, input_key, started_at FROM analysis_runs WHERE asset_id=?", (aid,))}


@pytest.mark.parametrize("change", ("version", "config"))
def test_a_changed_analyser_changes_its_key_and_its_dependants_keys_only(lib, monkeypatch, change):
    s, _ = lib
    before = _chain_keys(s, "h")
    motion = registry.get("motion")
    if change == "version":
        monkeypatch.setattr(motion, "version", motion.version + "+test")
    else:
        monkeypatch.setattr(motion, "config", lambda settings: {"threshold": "changed"})
    after = _chain_keys(s, "h")
    changed = {n for n in before if before[n] != after[n]}
    assert changed == {"motion"} | _descendants("motion")
    assert "caption" in changed and "proxy" not in changed and "speech" not in changed


def test_an_unchanged_file_plans_nothing(processed):
    s, db, a = processed
    assert pipeline.plan_asset(db, s, a["id"]) == []
    assert pipeline.plan_all(db, s) == 0
    assert db.q1("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")["n"] == 0


def test_a_version_bump_reruns_the_analyser_and_its_dependants_only(processed, monkeypatch):
    s, db, a = processed
    before = _runs(db, a["id"])
    motion = registry.get("motion")
    monkeypatch.setattr(motion, "version", motion.version + "+test")
    # Dependants wait for the analyser they depend on: only motion is planned at first.
    assert pipeline.plan_asset(db, s, a["id"]) == ["motion"]
    run_all(s, db)
    after = _runs(db, a["id"])
    rerun = {n for n in after if after[n] != before[n]}
    assert rerun == {"motion"} | _descendants("motion")
    assert pipeline.plan_asset(db, s, a["id"]) == []


def test_an_unavailable_analyser_runs_once_its_model_appears(processed, monkeypatch):
    s, db, a = processed
    assert db.q1("SELECT status FROM analysis_runs WHERE asset_id=? AND analyser='speech'", (a["id"],))["status"] == "unavailable"
    before = _runs(db, a["id"])
    speech = registry.get("speech")
    monkeypatch.setattr(speech, "check", lambda settings: None)  # the model is installed now
    monkeypatch.setattr(speech, "run", lambda ctx: {"segments": 0})
    assert pipeline.plan_all(db, s) == 1
    assert db.q1("SELECT analyser FROM jobs WHERE status='queued'")["analyser"] == "speech"
    run_all(s, db)
    assert db.q1("SELECT status FROM analysis_runs WHERE asset_id=? AND analyser='speech'", (a["id"],))["status"] == "done"
    # Its dependants were re-planned against the new speech output; nothing else re-ran.
    after = _runs(db, a["id"])
    assert {n for n in after if after[n] != before[n]} == {"speech"} | _descendants("speech")
    assert pipeline.plan_asset(db, s, a["id"]) == []


def test_a_changed_file_replans_everything(processed):
    s, db, a = processed
    before = _runs(db, a["id"])
    db.x("UPDATE assets SET content_hash=? WHERE id=?", ("changed-" + (a["content_hash"] or ""), a["id"]))
    roots = [x.name for x in registry.topological() if not x.requires]
    assert sorted(pipeline.plan_asset(db, s, a["id"])) == sorted(roots)
    run_all(s, db)
    after = _runs(db, a["id"])
    assert set(after) == set(before) and all(after[n][0] != before[n][0] for n in before)
