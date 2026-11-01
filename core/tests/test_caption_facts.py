from types import SimpleNamespace

from metachlorian.analysers.base import AnalysisContext
from metachlorian.analysers.caption import CaptionAnalyser, facts_for
from metachlorian.db import dumps


def test_caption_measurements_are_stable_after_fusion(lib):
    s, db = lib
    db.x("INSERT INTO assets(uid,path,filename,size,mtime,quick_hash,status,created_at,updated_at) "
         "VALUES('a','/a.mp4','a.mp4',1,0,'q','new',0,0)")
    asset = dict(db.q1('SELECT * FROM assets'))
    ctx = AnalysisContext(db, s, asset, CaptionAnalyser())
    shot = SimpleNamespace(id=7, duration=5.0)
    def signal(name, value, source):
        db.x("INSERT INTO signals(level,target_id,asset_id,name,value,source,confidence,model_version,created_at) "
             "VALUES('shot',?,?,?,?,?,1,'1',0)", (shot.id, asset['id'], name, dumps(value), source))
    signal('camera.movement', [{'term': 'pan_right'}], 'motion')
    signal('people.count', 2, 'people')
    signal('audio.transcript', 'Hello.', 'speech')
    signal('content.ocr_text', 'Entrance', 'ocr')
    original = facts_for(ctx, shot)
    assert 'Person detector count: 2.' in original
    assert 'optical flow): pan_right.' in original
    signal('camera.movement', [{'term': 'aerial'}, {'term': 'pan_right'}], 'fusion')
    signal('people.count', {'value': 2, 'sources': ['people']}, 'fusion')
    assert facts_for(ctx, shot) == original
