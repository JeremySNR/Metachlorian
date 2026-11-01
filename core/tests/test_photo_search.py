import json

import numpy as np
import pytest

from metachlorian.db import now
from metachlorian.photos.search import PhotoSearch
from .test_photos import photos


def test_ann_cache_reload_incremental_update_and_deleted_vectors(photos, monkeypatch):
    service, bridge, uid = photos
    db = service.db
    with db.tx() as c:
        for i in range(2, 2105):
            c.execute("INSERT INTO assets(id,uid,path,filename,media_kind,created_at,updated_at) VALUES(?,?,?,?, 'photo',1,1)", (i,f'a{i}',f'/offline/{i}.raw',f'{i}.raw'))
            c.execute('INSERT INTO photos(id,uid,asset_id,created_at,updated_at) VALUES(?,?,?,1,1)', (i,f'p{i}',i))
        matrix = np.random.default_rng(1).normal(size=(2104,8)).astype(np.float32)
        matrix /= np.linalg.norm(matrix,axis=1,keepdims=True)
        c.executemany("INSERT INTO photo_vectors(photo_id,model,dim,vec,updated_at) VALUES(?,'fixture',8,?,1)", ((i+1, v.astype(np.float16).tobytes()) for i,v in enumerate(matrix)))
    monkeypatch.setattr('metachlorian.photos.search.models.installed', lambda *_: True)
    monkeypatch.setattr('metachlorian.media.siglip.text_vector', lambda *_: matrix[99])
    search = service.searcher
    result = search.search('subject', diverse=False)
    assert result['results'][0]['id'] == 100
    path = search._cache_path
    assert path.exists()
    restarted = PhotoSearch(db, service.settings)
    assert restarted.search('subject', diverse=False)['results'][0]['id'] == 100
    # Replace the winning vector after cache creation, including same-count delete/insert.
    db.x('DELETE FROM photo_vectors WHERE photo_id=100')
    db.x("INSERT INTO photo_vectors(photo_id,model,dim,vec,updated_at) VALUES(100,'fixture',8,?,?)", ((-matrix[99]).astype(np.float16).tobytes(), now()))
    db.x('UPDATE photo_vectors SET vec=?,updated_at=? WHERE photo_id=101', (matrix[99].astype(np.float16).tobytes(), now()))
    assert restarted.search('subject', diverse=False)['results'][0]['id'] == 101
    db.x('DELETE FROM photo_vectors WHERE photo_id=101')
    assert restarted.search('subject', diverse=False)['results'][0]['id'] != 101
    # Corruption cannot turn into an authoritative index or crash search.
    path.write_bytes(b'broken')
    repaired = PhotoSearch(db, service.settings)
    assert repaired.search('subject', diverse=False)['semantic_available']
    assert path.stat().st_size > 6
    # Small filtered sets take the exact scoring branch.
    assert repaired.search('subject', filters={'min_rating': 1})['results'] == []
    result = repaired._vectors('subject', {1,2,3}, 3)
    assert set(result) == {1,2,3}


@pytest.mark.parametrize('filters', [{'min_rating': 6}, {'min_rating': True}, {'person_id': 'one'}, {'folder': []}, {'virtual_copies': 'yes'}])
def test_filter_types_are_validated(photos, filters):
    service, _, _ = photos
    with pytest.raises(ValueError):
        service.searcher.search(filters=filters)
