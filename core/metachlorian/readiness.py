"""Cheap, read-only coverage diagnostics; indexing is not evidence of analysis accuracy."""
from __future__ import annotations

from .capture_dates import capture_iso
from .db import Database, loads, now
from .jobs.queue import CURRENT_JOBS


def library_readiness(db: Database, limit: int = 10) -> dict:
    limit = max(1, min(50, limit))
    rows = db.q("SELECT a.id, a.uid, a.filename, a.status, a.tech, m.value index_state, "
                "(SELECT COUNT(*) FROM shots s WHERE s.asset_id=a.id AND s.active=1) active_shots, "
                "(SELECT COUNT(*) FROM shots s JOIN shot_index si ON si.shot_id=s.id WHERE s.asset_id=a.id AND s.active=1) indexed_shots, "
                "EXISTS(SELECT 1 FROM analysis_runs r WHERE r.asset_id=a.id AND r.analyser='proxy' AND r.status='done') preview "
                "FROM assets a LEFT JOIN meta m ON m.key='index:asset:' || a.id WHERE a.deleted_at IS NULL AND a.media_kind='video'")
    files = {k: 0 for k in ('total', 'searchable', 'fully_indexed', 'partially_indexed', 'unindexed', 'previews_ready',
                          'index_pending', 'index_failed', 'capture_date_known', 'capture_date_unknown')}
    shots = {'active': 0, 'indexed': 0, 'missing_from_index': 0}
    status: dict[str, int] = {}
    index_issues = []
    for r in rows:
        files['total'] += 1
        active, indexed = r['active_shots'], r['indexed_shots']
        shots['active'] += active
        shots['indexed'] += indexed
        shots['missing_from_index'] += active - indexed
        files['searchable'] += indexed > 0
        files['fully_indexed'] += active > 0 and active == indexed
        files['partially_indexed'] += 0 < indexed < active
        files['unindexed'] += indexed == 0
        files['previews_ready'] += r['preview']
        known = bool(capture_iso((loads(r['tech'], {}) or {}).get('capture_date')))
        files['capture_date_known' if known else 'capture_date_unknown'] += 1
        status[r['status']] = status.get(r['status'], 0) + 1
        marker = loads(r['index_state'], {}) or {}
        if marker.get('status') in ('pending', 'failed'):
            files['index_' + marker['status']] += 1
        if marker or indexed < active:
            index_issues.append({'asset_uid': r['uid'], 'filename': r['filename'], 'active_shots': active,
                                 'indexed_shots': indexed, 'status': marker.get('status', 'incomplete'),
                                 'error': (marker.get('error') or '')[:500], 'next_retry_at': marker.get('next_retry_at')})
    analysis: dict[str, dict[str, int]] = {}
    for r in db.q("SELECT r.analyser, r.status, COUNT(*) n FROM analysis_runs r JOIN assets a ON a.id=r.asset_id "
                  "WHERE a.deleted_at IS NULL GROUP BY r.analyser,r.status"):
        analysis.setdefault(r['analyser'], {})[r['status']] = r['n']
    failed_assets = db.q1("SELECT COUNT(DISTINCT r.asset_id) n FROM analysis_runs r JOIN assets a ON a.id=r.asset_id "
                         "WHERE a.deleted_at IS NULL AND r.status='failed'")['n']
    unavailable_assets = db.q1("SELECT COUNT(DISTINCT r.asset_id) n FROM analysis_runs r JOIN assets a ON a.id=r.asset_id "
                              "WHERE a.deleted_at IS NULL AND r.status='unavailable'")['n']
    jobs = {r['status']: r['n'] for r in db.q(
        "SELECT jobs.status,COUNT(*) n FROM jobs JOIN assets a ON a.id=jobs.asset_id "
        f"WHERE a.deleted_at IS NULL AND {CURRENT_JOBS} AND jobs.status IN ('queued','running','failed') GROUP BY jobs.status")}
    failures = [dict(r) for r in db.q(
        "SELECT a.uid asset_uid,a.filename,r.analyser,substr(r.error,1,500) error FROM analysis_runs r "
        "JOIN assets a ON a.id=r.asset_id WHERE a.deleted_at IS NULL AND r.status='failed' ORDER BY r.finished_at DESC LIMIT ?", (limit,))]
    scans = []
    for r in db.q("SELECT id,uri,last_scan FROM sources WHERE kind<>'photos' ORDER BY id"):
        scan = loads(db.get_meta(f"scan:{r['id']}"), {}) or {}
        scans.append({'source_id': r['id'], 'path': r['uri'], 'state': scan.get('state', 'not_scanned'),
                      'last_scan': r['last_scan']})
    busy = bool(jobs.get('queued') or jobs.get('running') or any(s['state'] in ('queued', 'discovering', 'registering') for s in scans))
    attention = bool(failed_assets or jobs.get('failed') or files['index_failed'] or status.get('error') or status.get('missing')
                     or any(s['state'] in ('failed', 'completed_with_errors') for s in scans)
                     or ((shots['missing_from_index'] or files['unindexed']) and not busy))
    state = 'attention' if attention else 'processing' if busy or files['index_pending'] else 'available' if rows else 'empty'
    return {'checked_at': now(), 'state': state, 'files': files, 'shots': shots, 'status': status, 'jobs': jobs,
            'analysis': analysis, 'failed_analysis_files': failed_assets, 'limited_analysis_files': unavailable_assets,
            'index_issues': index_issues[:limit], 'index_issues_total': len(index_issues), 'failures': failures,
            'sources': scans, 'notes': [
                'Searchable means at least one active shot is indexed; it does not mean every analyser succeeded.',
                'Unavailable analysis can mean an optional model or provider is disabled. Check analysis counts before relying on that feature.',
                'An empty search is not proof footage is absent while scans, analysis or indexing are incomplete.',
            ]}
