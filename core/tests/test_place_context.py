import pytest

from metachlorian.place_context import capture_seconds, infer_places


def shot(sid, aid=None, capture=100, duration=10, start=0, end=10, recognition=None, **kw):
    aid = sid if aid is None else aid
    return {"id": sid, "uid": f"shot-{sid}", "asset_id": aid, "asset_uid": f"asset-{aid}",
            "capture": None if capture is None else (capture, False), "asset_duration": duration,
            "start_s": start, "end_s": end, "folder": "/trip/day", "camera": "Sony", "original": True,
            "recognition": recognition or {}, **kw}


def place(name="Mickey Mouse Clubhouse Live!", confidence="high", evidence=None):
    return {"name": name, "confidence": confidence, "relationship": "recording_location",
            "evidence": ["Distinctive stage and readable title"] if evidence is None else evidence}


def test_five_second_gap_uses_end_of_take_and_keeps_provenance():
    rows = [shot(1, recognition={"attraction_or_show": place()}), shot(2, capture=115)]
    rec = infer_places(rows)[2]["attraction_or_show"]
    assert rec["method"] == "inherited" and rec["gap_seconds"] == 5
    assert rec["anchor_shot_uid"] == "shot-1" and rec["anchor_asset_uid"] == "asset-1"
    assert 0.85 < rec["confidence"] < 0.9 and not rec["anchor_eligible"]


def test_inheritance_is_not_transitive():
    rows = [shot(1, recognition={"venue": place("Hollywood Studios")}), shot(2, capture=115), shot(3, capture=130)]
    result = infer_places(rows)
    assert "venue" in result[2] and "venue" not in result[3]


@pytest.mark.parametrize("change", [{"capture": None}, {"capture": (100, False)}, {"capture": (200, False)},
                                    {"folder": "/other"}, {"camera": "Other"}, {"capture": (115, True)}, {"original": False}])
def test_missing_clock_overlap_long_gap_folder_camera_and_non_original_do_not_inherit(change):
    target = shot(2, capture=115)
    target.update(change)
    assert infer_places([shot(1, recognition={"venue": place("Hollywood Studios")}), target])[2] == {}


@pytest.mark.parametrize("confidence,evidence", [("probable", ["Similar stage"]), ("unknown", ["Sign"]), ("high", [])])
def test_only_high_with_evidence_can_anchor(confidence, evidence):
    rows = [shot(1, recognition={"venue": place("Hollywood Studios", confidence, evidence)}), shot(2, capture=115)]
    assert infer_places(rows)[2] == {}


def test_conflicting_neighbours_remain_unresolved():
    rows = [shot(1, recognition={"venue": place("Magic Kingdom")}), shot(2, capture=115),
            shot(3, capture=130, recognition={"venue": place("Hollywood Studios")})]
    assert infer_places(rows)[2] == {}


@pytest.mark.parametrize('relationship', ['visible_landmark', 'unclear', None])
def test_visible_or_unscoped_attraction_does_not_label_nearby_family_shots(relationship):
    landmark = place('Space Mountain')
    if relationship is None:
        landmark.pop('relationship')  # compatibility with older scan records
    else:
        landmark['relationship'] = relationship
    rows = [shot(1, recognition={'venue':place('Magic Kingdom'),'attraction_or_show':landmark}),
            shot(2, capture=115)]
    result = infer_places(rows)
    assert result[1]['attraction_or_show']['value'] == 'Space Mountain'
    assert not result[1]['attraction_or_show']['anchor_eligible']
    assert result[2]['venue']['value'] == 'Magic Kingdom'
    assert 'attraction_or_show' not in result[2]


def test_conflicting_parent_blocks_show_and_direct_guess_is_preserved():
    anchor = shot(1, recognition={"venue": place("Hollywood Studios"), "attraction_or_show": place()})
    target = shot(2, capture=115, recognition={"venue": place("Magic Kingdom", "probable")})
    rec = infer_places([anchor, target])[2]
    assert rec["venue"]["method"] == "direct" and "attraction_or_show" not in rec


def test_same_camera_take_can_use_nearby_shot_without_timestamp():
    rows = [shot(1, aid=1, capture=None, duration=20, end=10, recognition={"venue": place("Hollywood Studios")}),
            shot(2, aid=1, capture=None, duration=20, start=10, end=20)]
    assert infer_places(rows)[2]["venue"]["gap_seconds"] == 0


def test_a_long_take_does_not_carry_an_early_show_indefinitely():
    rows = [shot(1, duration=120, end=5, recognition={"attraction_or_show": place()}), shot(2, capture=225)]
    assert infer_places(rows)[2] == {}


def test_manual_empty_label_can_block_inheritance():
    target = shot(2, capture=115, blocked_levels=["venue"])
    assert infer_places([shot(1, recognition={"venue": place("Hollywood Studios")}), target])[2] == {}


def test_camera_datetime_formats_and_invalid_times():
    assert capture_seconds("2026:10:04 12:31:05") == capture_seconds("2026-10-04T12:31:05")
    assert capture_seconds("2026-10-04T12:31:05Z")[1] is True
    assert capture_seconds("2026-10-04T08:31:05-04:00") == capture_seconds("2026-10-04T12:31:05Z")
    assert capture_seconds("garbage") is None and capture_seconds(None) is None


def test_intervening_conflicting_venue_blocks_narrower_show():
    rows = [shot(1, aid=1, end=2, recognition={"venue": place("Hollywood Studios"), "attraction_or_show": place()}),
            shot(2, aid=1, start=2, end=4, recognition={"venue": place("Magic Kingdom")}),
            shot(3, aid=1, start=4, end=6)]
    assert "attraction_or_show" not in infer_places(rows)[3]


def test_database_refresh_is_searchable_idempotent_and_removes_deleted_anchor(processed, tmp_path):
    from metachlorian.db import dumps, now
    from metachlorian.ingest.scan import register_file
    from metachlorian.place_context import refresh_places
    from metachlorian.records import record_correction

    s, db, a = processed
    db.x("UPDATE sources SET options=? WHERE id=?", (dumps({"camera_originals": True}), a["source_id"]))
    tech = {"capture_date": "2026:10:04 12:00:00", "width": 320, "height": 180}
    db.x("UPDATE assets SET tech=? WHERE id=?", (dumps(tech), a["id"]))
    seed = db.q1("SELECT * FROM shots WHERE asset_id=? ORDER BY idx DESC LIMIT 1", (a["id"],))
    record = {"place_recognition": {"attraction_or_show": place()}}
    db.x("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at) "
         "VALUES('shot',?,?, 'vlm.record',?, 'caption', .9, 'test',?)", (seed["id"], a["id"], dumps(record), now()))
    path = tmp_path / "second.mp4"
    path.write_bytes(b"unique fixture bytes")
    _, aid = register_file(db, path, a["source_id"])
    # Same folder group as the original, but preserve distinct fixture contents.
    db.x("UPDATE assets SET path=?,duration=2,tech=? WHERE id=?", (str(__import__('pathlib').Path(a["path"]).parent / 'second.mp4'),
         dumps({**tech, "capture_date": "2026:10:04 12:00:11"}), aid))
    db.x("INSERT INTO shots(uid,asset_id,idx,start_s,end_s,start_frame,end_frame,segmenter) VALUES('target',?,0,0,2,0,50,'test')", (aid,))
    result = refresh_places(db, s)
    assert result["inherited_fields"] > 0
    target = db.q1("SELECT id FROM shots WHERE uid='target'")[0]
    assert 'Mickey Mouse Clubhouse' in db.q1("SELECT place FROM shot_fts WHERE rowid=?", (target,))[0]
    assert refresh_places(db, s)["changed_fields"] == 0
    record_correction(db, 'shot', a['uid'], 'content.attraction_or_show', 'set', 'Confirmed Show', 'reviewer', None, seed['uid'])
    refresh_places(db, s)
    assert 'Confirmed Show' in db.q1("SELECT place FROM shot_fts WHERE rowid=?", (target,))[0]
    db.x("UPDATE assets SET deleted_at=? WHERE id=?", (now(), a["id"]))
    refresh_places(db, s)
    assert db.q1("SELECT COUNT(*) FROM signals WHERE target_id=? AND source='place_context'", (target,))[0] == 0
