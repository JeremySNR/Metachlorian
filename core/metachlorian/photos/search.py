"""Hybrid local retrieval; the agent compares shortlisted photographs visually."""
from __future__ import annotations

import re
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import numpy as np

from .. import models
from ..db import loads


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


class PhotoSearch:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self._lock = threading.RLock()
        self._index = None
        self._stamp = None
        self._saved_at = float('-inf')
        self._cache_path = Path(settings.data_dir) / "photo-index" / "semantic.usearch"

    def warm(self):
        row = self.db.q1('SELECT dim FROM photo_vectors LIMIT 1')
        if row:
            with self._lock:
                self._sync_index(row['dim'])

    def _sync_index(self, dim: int):
        from usearch.index import Index
        stamp = tuple(self.db.q1('SELECT COUNT(*),MAX(updated_at) FROM photo_vectors'))
        path, meta_path = self._cache_path, self._cache_path.with_suffix('.json')
        if self._index is None and path.is_file() and meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text())
                if meta['dim'] == dim and meta['version'] == 1 and _digest(path) == meta['sha256']:
                    self._index = Index.restore(str(path), view=False)
                    self._stamp = tuple(meta['stamp'])
                    self._saved_at = time.monotonic()
            except (OSError, ValueError, KeyError, RuntimeError):
                self._index = self._stamp = None
        changed = self._index is None or stamp != self._stamp
        if self._index is None:
            self._index = Index(ndim=dim, metric='cos', dtype='f16', connectivity=16, expansion_add=64, expansion_search=96)
            rows = self.db.q('SELECT photo_id,vec FROM photo_vectors WHERE dim=?', (dim,))
            for start in range(0, len(rows), 512):
                batch = rows[start:start+512]
                self._index.add(np.array([r['photo_id'] for r in batch], dtype=np.uint64),
                                np.stack([np.frombuffer(r['vec'], np.float16) for r in batch]), threads=2)
        elif stamp != self._stamp:
            # Remove obsolete keys too: a delete and insert can keep the count
            # unchanged. SQLite remains the authority, including across restarts.
            alive = {r[0] for r in self.db.q('SELECT photo_id FROM photo_vectors WHERE dim=?', (dim,))}
            gone = set(int(k) for k in self._index.keys) - alive
            if gone:
                self._index.remove(np.array(list(gone), dtype=np.uint64))
            rows = self.db.q('SELECT photo_id,vec FROM photo_vectors WHERE dim=? AND updated_at>=?', (dim, self._stamp[1] or 0))
            for row in rows:
                key = row['photo_id']
                if self._index.contains(key):
                    self._index.remove(key)
                self._index.add(key, np.frombuffer(row['vec'], np.float16), threads=1)
        self._stamp = stamp
        if changed and time.monotonic() - self._saved_at > 60:
            # Checksum validates the two-file cache even after an interrupted
            # save. Atomic rename leaves SQLite and the last cache recoverable.
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f'.{os.getpid()}.tmp')
            self._index.save(str(temporary))
            digest = _digest(temporary)
            temporary.replace(path)
            temporary = meta_path.with_suffix(f'.{os.getpid()}.tmp')
            temporary.write_text(json.dumps({'version': 1, 'dim': dim, 'stamp': stamp, 'sha256': digest}))
            temporary.replace(meta_path)
            self._saved_at = time.monotonic()

    def _vectors(self, query: str, wanted: set[int], count: int) -> list[int]:
        if not models.installed(self.settings.resolved_models_dir, 'siglip-base-multilingual'):
            return []
        from ..media.siglip import text_vector
        vector = text_vector(str(self.settings.resolved_models_dir), query)
        # Filtered small sets are exact, avoiding ANN post-filter starvation.
        if len(wanted) <= 2000:
            scored = []
            ids = list(wanted)
            for start in range(0, len(ids), 500):
                batch = ids[start:start+500]
                rows = self.db.q(f"SELECT photo_id,dim,vec FROM photo_vectors WHERE photo_id IN ({','.join('?' for _ in batch)})", batch)
                scored.extend((float(np.frombuffer(r['vec'], np.float16).astype(np.float32) @ vector), r['photo_id']) for r in rows if r['dim'] == len(vector))
            return [pid for _, pid in sorted(scored, reverse=True)[:count]]
        with self._lock:
            self._sync_index(len(vector))
            limit = min(max(count*4, 256), len(self._index))
            selected = []
            while limit:
                matches = self._index.search(vector, count=limit)
                selected = [int(k) for k in matches.keys if int(k) in wanted]
                if len(selected) >= count or limit == len(self._index):
                    break
                limit = min(limit*4, len(self._index))
            return selected[:count]

    def search(self, query: str = '', filters: dict | None = None, limit: int = 40, cursor: str | None = None, diverse: bool = True) -> dict:
        start = time.monotonic()
        filters = filters or {}
        known = {'catalog_uid', 'folder', 'person_id', 'person', 'date_from', 'date_to', 'min_rating', 'camera', 'lens', 'burst_id', 'availability', 'collection', 'virtual_copies'}
        if set(filters) - known:
            raise ValueError('Unknown photo filters: ' + ', '.join(sorted(set(filters)-known)))
        for key, value in filters.items():
            if value is None:
                continue
            if key in {'person_id', 'min_rating'}:
                if type(value) is not int or (key == 'min_rating' and not 0 <= value <= 5) or (key == 'person_id' and value < 1):
                    raise ValueError('Invalid numeric photo filter: '+key)
            elif key == 'virtual_copies':
                if type(value) is not bool:
                    raise ValueError('virtual_copies must be a boolean')
            elif not isinstance(value, str) or len(value) > 2000:
                raise ValueError('Invalid text photo filter: '+key)
        limit, offset = max(1, min(int(limit), 100)), int(cursor or 0)
        if offset < 0 or len(query) > 2000:
            raise ValueError('Invalid search cursor or query length')
        where, args = ['p.deleted_at IS NULL', 'a.deleted_at IS NULL'], []
        for key, column in [('catalog_uid','p.catalog_uid'), ('camera','p.camera'), ('lens','p.lens'), ('burst_id','p.burst_id'), ('availability','p.availability')]:
            if filters.get(key) is not None:
                where.append(column+'=?')
                args.append(filters[key])
        for key, comparison in [('date_from','>='), ('date_to','<=')]:
            if filters.get(key):
                where.append('p.capture_time'+comparison+'?')
                args.append(str(filters[key]))
        if filters.get('min_rating') is not None:
            where.append('p.rating>=?')
            args.append(int(filters['min_rating']))
        if filters.get('folder'):
            where.append("replace(a.path, '\\', '/') LIKE ? ESCAPE '\\'")
            value = str(filters['folder']).replace('\\', '/').replace('%','\\%').replace('_','\\_')
            args.append(value.rstrip('/')+'/%')
        if filters.get('person_id') is not None or filters.get('person'):
            cond = 'f.identity_id=?' if filters.get('person_id') is not None else 'lower(i.name)=lower(?)'
            where.append('EXISTS (SELECT 1 FROM photo_faces f JOIN identities i ON i.id=f.identity_id WHERE f.photo_id=p.id AND '+cond+')')
            args.append(filters.get('person_id') if filters.get('person_id') is not None else filters['person'])
        if filters.get('collection'):
            where.append('EXISTS (SELECT 1 FROM photo_collection_items ci JOIN collections c ON c.id=ci.collection_id WHERE ci.photo_id=p.id AND (c.uid=? OR c.name=?))')
            args.extend([filters['collection']]*2)
        if filters.get('virtual_copies') is False:
            where.append('p.is_virtual=0')
        base = ' FROM photos p JOIN assets a ON a.id=p.asset_id WHERE '+' AND '.join(where)
        rows = self.db.q('SELECT p.id,p.asset_id,p.rating,p.capture_time,p.burst_id'+base+' ORDER BY p.rating DESC,p.capture_time DESC,p.id DESC', args)
        by_id = {r['id']: r for r in rows}
        ranks: dict[int, float] = {}
        semantic = False
        if query.strip():
            words = re.findall(r'\w+', query, flags=re.UNICODE)
            lexical = []
            if words:
                expression = ' OR '.join('"'+word+'"' for word in words)
                lexical = [r['rowid'] for r in self.db.q('SELECT rowid FROM photo_fts WHERE photo_fts MATCH ? ORDER BY rank LIMIT 2000', (expression,)) if r['rowid'] in by_id]
            visual = self._vectors(query, set(by_id), 1000) if by_id else []
            semantic = bool(visual)
            for ranking in (lexical, visual):
                for rank, pid in enumerate(ranking):
                    ranks[pid] = ranks.get(pid, 0) + 1/(60+rank+1)
            ordered = sorted(ranks, key=lambda pid: (ranks[pid], by_id[pid]['rating']), reverse=True)
        else:
            ordered = list(by_id)
        if diverse and not filters.get('burst_id'):
            seen, distinct = set(), []
            for pid in ordered:
                row = by_id[pid]
                group = row['burst_id'] or f"asset:{row['asset_id']}"
                if group not in seen:
                    seen.add(group)
                    distinct.append(pid)
            ordered = distinct
        results = []
        for pid in ordered[offset:offset+limit]:
            row = dict(self.db.q1('SELECT p.id,p.uid,p.asset_id,p.rating,p.capture_time,p.burst_id,p.evidence,p.availability,p.is_virtual,p.copy_name,p.status,p.revision,a.filename,a.width,a.height FROM photos p JOIN assets a ON a.id=p.asset_id WHERE p.id=?', (pid,)))
            evidence = loads(row.pop('evidence'), {})
            row['why'] = {'relevance': ranks.get(pid), 'rating': row['rating'], 'burst_id': row['burst_id'],
                          'technical_evidence': {k: evidence.get(k) for k in ('exposure','global_sharpness')},
                          'uncertainty': evidence.get('uncertainty', ['Not yet analysed']), 'visual_review_required': True}
            row['preview_url'] = '/api/photos/'+row['uid']+'/preview'
            results.append(row)
        return {'results': results, 'total': len(ordered), 'next_cursor': str(offset+limit) if offset+limit < len(ordered) else None,
                'semantic_available': semantic if query else models.installed(self.settings.resolved_models_dir, 'siglip-base-multilingual'),
                'retrieval_limit': 2000 if query else None, 'timings_ms': {'total': round((time.monotonic()-start)*1000, 1)}}
