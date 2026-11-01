"""Agent workflows through the real in-memory MCP transport, without external providers."""
import json

import anyio

from metachlorian.auth import AGENT_DEFAULT, Principal
from metachlorian.db import dumps
from metachlorian.ingest.scan import register_file
from metachlorian.service import Library


def agent(*extra):
    return Principal(None, 'workflow-agent', 'agent', set(AGENT_DEFAULT) | set(extra), 'mcp')


def payload(result):
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def test_file_pagination_includes_unprocessed_and_sorts_camera_dates(lib, tmp_path, mcp_client):
    settings, db = lib
    for filename, captured in [('newest.mp4', '2026:10:25 17:58:44+00:00'),
                               ('oldest.mp4', '2017-10-19T12:00:00Z'),
                               ('unknown.mp4', '0000:00:00 00:00:00')]:
        path = tmp_path / filename
        path.write_bytes(filename.encode())
        _, aid = register_file(db, path)
        db.x('UPDATE assets SET tech=? WHERE id=?', (dumps({'capture_date': captured}), aid))

    async def go():
        async with mcp_client(Library(db, settings), agent()) as client:
            first = payload(await client.call_tool('list_files', {'sort': 'captured_asc', 'limit': 2}))
            assert first['total'] == 3 and first['has_more'] and first['next_offset'] == 2
            assert [a['filename'] for a in first['assets']] == ['oldest.mp4', 'newest.mp4']
            assert all(not a['preview_ready'] for a in first['assets'])
            last = payload(await client.call_tool('list_files', {'sort': 'captured_asc', 'limit': 2, 'offset': first['next_offset']}))
            assert [a['filename'] for a in last['assets']] == ['unknown.mp4']
            assert last['next_offset'] is None and not last['has_more']
            default = payload(await client.call_tool('list_files', {'limit': 1}))
            assert default['assets'][0]['filename'] == 'unknown.mp4'  # import order remains the default
            bad = await client.call_tool('list_files', {'sort': 'not-a-sort'})
            assert bad.is_error

    anyio.run(go)


def test_collection_shortlist_workflow_is_scoped_and_audited(processed, mcp_client):
    settings, db, asset = processed
    library = Library(db, settings)
    shots = [r['uid'] for r in db.q('SELECT uid FROM shots WHERE asset_id=? ORDER BY idx', (asset['id'],))]

    async def go():
        async with mcp_client(library, agent()) as client:
            denied = await client.call_tool('create_collection', {'name': 'No permission'})
            assert denied.is_error and 'collections:write' in denied.content[0].text
            assert db.q1('SELECT COUNT(*) n FROM collections')['n'] == 0
        async with mcp_client(library, agent('collections:write')) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            for name in ('create_collection', 'add_to_collection'):
                assert tools[name].annotations.idempotent_hint is False
                assert tools[name].annotations.read_only_hint is False
            shortlist = payload(await client.call_tool('create_collection', {'name': 'Holiday selects', 'brief': 'A calm opening'}))
            uid = shortlist['uid']
            selected = payload(await client.call_tool('add_to_collection', {
                'collection_id': uid, 'shot_ids': shots[:2], 'note': 'Establish the setting',
            }))
            assert [i['shot']['uid'] for i in selected['items']] == shots[:2]
            assert all(i['note'] == 'Establish the setting' for i in selected['items'])
            ids = [i['item_id'] for i in selected['items']]
            refined = payload(await client.call_tool('update_collection_item', {
                'collection_id': uid, 'item_id': ids[0], 'note': 'Hold the opening', 'in_seconds': 0.25, 'out_seconds': 1.5,
            }))
            assert refined['items'][0]['in'] == 0.25 and refined['items'][0]['out'] == 1.5
            note_only = payload(await client.call_tool('update_collection_item', {
                'collection_id': uid, 'item_id': ids[0], 'note': '',
            }))
            assert note_only['items'][0]['in'] == 0.25 and note_only['items'][0]['note'] == ''
            reset = payload(await client.call_tool('update_collection_item', {
                'collection_id': uid, 'item_id': ids[0], 'reset_trim': True,
            }))
            assert reset['items'][0]['in'] is None and reset['items'][0]['out'] is None
            ambiguous = await client.call_tool('update_collection_item', {
                'collection_id': uid, 'item_id': ids[0], 'reset_trim': True, 'in_seconds': 1,
            })
            assert ambiguous.is_error
            reordered = payload(await client.call_tool('reorder_collection', {'collection_id': uid, 'item_ids': ids[::-1]}))
            assert [i['item_id'] for i in reordered['items']] == ids[::-1]
            bad_order = await client.call_tool('reorder_collection', {'collection_id': uid, 'item_ids': [ids[0], ids[0]]})
            assert bad_order.is_error
            still_ordered = payload(await client.call_tool('get_collection', {'collection_id': uid}))
            assert [i['item_id'] for i in still_ordered['items']] == ids[::-1]
            failed = await client.call_tool('add_to_collection', {'collection_id': uid, 'shot_ids': [shots[-1], 'missing-shot']})
            assert failed.is_error
            unchanged = payload(await client.call_tool('get_collection', {'collection_id': uid}))
            assert len(unchanged['items']) == 2  # invalid batches must not partly append
            updated = payload(await client.call_tool('update_collection', {'collection_id': uid, 'name': 'Opening selects', 'brief': ''}))
            assert updated['name'] == 'Opening selects' and updated['brief'] == ''
            removed = payload(await client.call_tool('remove_from_collection', {'collection_id': uid, 'item_id': selected['items'][0]['item_id']}))
            assert [i['shot']['uid'] for i in removed['items']] == shots[1:2]
            other = payload(await client.call_tool('create_collection', {'name': 'Different shortlist'}))
            wrong_collection = await client.call_tool('remove_from_collection', {
                'collection_id': other['uid'], 'item_id': removed['items'][0]['item_id'],
            })
            assert wrong_collection.is_error
            assert len(payload(await client.call_tool('get_collection', {'collection_id': uid}))['items']) == 1
            assert db.q1('SELECT COUNT(*) n FROM shots WHERE asset_id=?', (asset['id'],))['n'] == len(shots)

    anyio.run(go)
    actions = {r['action'] for r in db.q("SELECT action FROM audit_log WHERE actor='workflow-agent'")}
    assert {'create_collection', 'add_to_collection', 'update_collection', 'update_collection_item',
            'reorder_collection', 'remove_from_collection'} <= actions


def test_agent_can_inspect_processing_and_page_shots_chronologically(processed, mcp_client):
    settings, db, asset = processed
    rows = db.q('SELECT shot_id FROM shot_index WHERE asset_id=? ORDER BY start_s', (asset['id'],))
    assert len(rows) >= 3
    for n, row in enumerate(rows):
        db.x('UPDATE shot_index SET capture_date=? WHERE shot_id=?', (f'2026:10:{n + 1:02d} 12:00:00', row['shot_id']))

    async def go():
        async with mcp_client(Library(db, settings), agent()) as client:
            compact = payload(await client.call_tool('get_asset', {'asset_id': asset['uid'], 'include_transcript': False}))
            assert 'processing' not in compact and 'transcript' not in compact
            detailed = payload(await client.call_tool('get_asset', {'asset_id': asset['uid'], 'include_processing': True}))
            assert detailed['processing'] and all('analyser' in run for run in detailed['processing'])
            newest = payload(await client.call_tool('search_shots', {'asset_ids': [asset['uid']], 'sort': 'captured_desc', 'limit': 1}))
            older = payload(await client.call_tool('search_shots', {'asset_ids': [asset['uid']], 'sort': 'captured_desc', 'limit': 1, 'cursor': newest['next_cursor']}))
            expected = db.q1('SELECT uid FROM shots WHERE id=?', (rows[-1]['shot_id'],))['uid']
            assert newest['results'][0]['uid'] == expected
            assert older['results'][0]['uid'] != expected

    anyio.run(go)


def test_readiness_distinguishes_unindexed_files_and_requires_read_scope(lib, tmp_path, mcp_client):
    settings, db = lib
    path = tmp_path / 'waiting.mp4'
    path.write_bytes(b'not analysed yet')
    register_file(db, path)
    library = Library(db, settings)

    async def go():
        async with mcp_client(library, Principal(None, 'no-read', 'agent', set(), 'mcp')) as client:
            denied = await client.call_tool('library_readiness', {})
            assert denied.is_error and 'library:read' in denied.content[0].text
        async with mcp_client(library, agent()) as client:
            readiness = payload(await client.call_tool('library_readiness', {'limit': 1}))
            assert readiness['files']['total'] == 1
            assert readiness['files']['searchable'] == 0 and readiness['files']['unindexed'] == 1
            assert readiness['shots']['indexed'] == 0
            assert 'analysis' in readiness and 'notes' in readiness
            assert db.q1('SELECT COUNT(*) n FROM jobs')['n'] == 0
            assert db.q1("SELECT COUNT(*) n FROM audit_log WHERE actor='workflow-agent' AND action='library_readiness'")['n'] == 1

    anyio.run(go)
