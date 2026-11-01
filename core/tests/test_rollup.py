from types import SimpleNamespace

import pytest

from metachlorian.analysers.base import AnalysisContext
from metachlorian.analysers.rollup import RollupAnalyser
from metachlorian.db import dumps


@pytest.mark.parametrize('value,expected', [(2, 1), (0, 0), ({'value': 2}, 1), (None, 0)])
def test_rollup_accepts_detector_and_fused_people_counts(lib, monkeypatch, value, expected):
    settings, db = lib
    db.x("INSERT INTO assets(uid,path,filename,size,mtime,quick_hash,status,created_at,updated_at) "
         "VALUES('a','/a.mp4','a.mp4',1,0,'q','new',0,0)")
    asset = dict(db.q1('SELECT * FROM assets'))
    analyser = RollupAnalyser()
    ctx = AnalysisContext(db, settings, asset, analyser)
    monkeypatch.setattr(ctx, 'shots', lambda: [SimpleNamespace(id=1, duration=5, end_s=5)])
    db.x("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at) "
         "VALUES('shot',1,?,'people.count',?,'people',1,'1',0)", (asset['id'], dumps(value)))
    analyser.run(ctx)
    assert ctx.asset_updates['summary']['people_shots'] == expected
