import pytest

from metachlorian.auth import LOCAL_ADMIN
from metachlorian.service import Library, NotFound


def test_collection_mutations_are_atomic_and_scoped(processed):
    settings, db, _ = processed
    service = Library(db, settings)
    shots = [r['uid'] for r in db.q('SELECT uid FROM shots ORDER BY idx')]
    a = service.create_collection(LOCAL_ADMIN, 'A')['uid']
    b = service.create_collection(LOCAL_ADMIN, 'B')['uid']
    with pytest.raises(NotFound):
        service.add_to_collection(LOCAL_ADMIN, a, [shots[0], 'does-not-exist'])
    assert service.collection(LOCAL_ADMIN, a)['items'] == []
    a_items = service.add_to_collection(LOCAL_ADMIN, a, shots[:2])['items']
    b_item = service.add_to_collection(LOCAL_ADMIN, b, shots[:1])['items'][0]['item_id']
    for action in (lambda: service.remove_item(LOCAL_ADMIN, a, b_item),
                   lambda: service.update_item(LOCAL_ADMIN, a, b_item, note='wrong collection')):
        with pytest.raises(NotFound):
            action()
    for bad in ([b_item], [a_items[0]['item_id']] * 2, [a_items[0]['item_id']]):
        with pytest.raises(ValueError):
            service.reorder(LOCAL_ADMIN, a, bad)
    ids = [i['item_id'] for i in a_items][::-1]
    ordered = service.reorder(LOCAL_ADMIN, a, ids)
    assert [i['item_id'] for i in ordered['items']] == ids
    service.update_item(LOCAL_ADMIN, a, ids[0], note='opening shot')
    assert service.collection(LOCAL_ADMIN, b)['items'][0]['note'] == ''
    assert {'reorder_collection', 'update_collection_item'} <= {r['action'] for r in db.q('SELECT action FROM audit_log')}


def test_collection_trims_are_validated_before_mutation(processed):
    settings, db, asset = processed
    service = Library(db, settings)
    shot = db.q1('SELECT uid FROM shots ORDER BY idx')['uid']
    uid = service.create_collection(LOCAL_ADMIN, 'Trim tests')['uid']
    for start, end in ((-1, 1), (2, 1), (0, asset['duration'] + 1), (float('nan'), 1), (0, float('inf'))):
        with pytest.raises(ValueError):
            service.add_to_collection(LOCAL_ADMIN, uid, [shot], start, end)
    assert service.collection(LOCAL_ADMIN, uid)['items'] == []
    item = service.add_to_collection(LOCAL_ADMIN, uid, [shot], 0, asset['duration'])['items'][0]
    # Handles beyond the named shot are allowed, but cannot leave the source file.
    with pytest.raises(ValueError):
        service.update_item(LOCAL_ADMIN, uid, item['item_id'], **{'out': -1, 'note': 'invalid'})
    assert service.collection(LOCAL_ADMIN, uid)['items'][0]['note'] == ''
    reset = service.update_item(LOCAL_ADMIN, uid, item['item_id'], **{'in': None, 'out': None})
    assert reset['items'][0]['in'] is None and reset['items'][0]['out'] is None
