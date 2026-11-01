"""Photo/variant identity and incremental ingestion, without copying files."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..db import Database, dumps, loads, now
from ..ingest.scan import new_uid
from .images import PHOTO_EXTENSIONS, fingerprint, metadata


def catalog(db: Database, info: dict):
    db.x('INSERT INTO photo_catalogs(uid,path,name,version) VALUES(?,?,?,?) '
         'ON CONFLICT(uid) DO UPDATE SET path=excluded.path,name=excluded.name,version=excluded.version',
         (info['uid'], info['path'], info['name'], info.get('version', '')))


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [str(x) for x in value or [] if isinstance(x, (str, int, float))]


def register(db: Database, path: str, meta: dict, *, catalog_uid: str | None = None, source_id: int | None = None) -> dict:
    p = Path(path).expanduser().resolve()
    path = os.path.normcase(str(p))
    stamp = now()
    try:
        stat = p.stat()
        size, mtime, file_key = stat.st_size, stat.st_mtime, fingerprint(p)
    except OSError:
        size = mtime = file_key = None
    lr_id = str(meta['lr_id']) if catalog_uid else None
    virtual = bool(meta.get('is_virtual'))
    dims = meta.get('dimensions') or {}
    if not isinstance(dims, dict):
        dims = {}
    width, height = dims.get('width', meta.get('ImageWidth')), dims.get('height', meta.get('ImageHeight'))
    keywords = sorted(set(_strings(meta.get('keywords', meta.get('Subject'))) + _strings(meta.get('keywordPaths'))))
    rating = max(0, min(5, int(meta.get('rating', meta.get('Rating', 0)) or 0)))
    sync_key = str(meta.get('last_edit_time', ''))
    with db.tx() as c:
        asset = c.execute('SELECT a.* FROM assets a JOIN asset_paths p ON p.asset_id=a.id WHERE p.path=?', (path,)).fetchone()
        if asset and asset['media_kind'] != 'photo':
            raise ValueError('This path is already registered as a video')
        if not asset:
            aid = c.execute('INSERT INTO assets(uid,source_id,path,filename,size,mtime,quick_hash,status,width,height,media_kind,created_at,updated_at) '
                            "VALUES(?,?,?,?,?,?,?,'ready',?,?,'photo',?,?)",
                            (new_uid('a'), source_id, path, p.name, size, mtime, file_key, width, height, stamp, stamp)).lastrowid
            c.execute('INSERT INTO asset_paths(asset_id,path,mtime,size,seen_at) VALUES(?,?,?,?,?)', (aid, path, mtime, size, stamp))
        else:
            aid = asset['id']
            c.execute('UPDATE assets SET size=?,mtime=?,quick_hash=?,width=COALESCE(?,width),height=COALESCE(?,height),updated_at=? WHERE id=?',
                      (size, mtime, file_key, width, height, stamp, aid))
            c.execute('UPDATE asset_paths SET seen_at=?,mtime=?,size=? WHERE path=?', (stamp, mtime, size, path))
        prior = c.execute('SELECT * FROM photos WHERE catalog_uid=? AND lr_id=?', (catalog_uid, lr_id)).fetchone() if catalog_uid else \
                c.execute('SELECT * FROM photos WHERE asset_id=? AND catalog_uid IS NULL', (aid,)).fetchone()
        if not prior and catalog_uid and not virtual:
            # Preserve a folder photo's uid when its existing file is first
            # linked to Lightroom; a virtual copy always gets its own identity.
            prior = c.execute('SELECT * FROM photos WHERE asset_id=? AND catalog_uid IS NULL', (aid,)).fetchone()
        oldmeta = loads(prior['metadata'], {}) if prior else {}
        merged = {**oldmeta, **meta, '_sync_key': sync_key, '_file_key': file_key}
        merged.pop('settings', None)  # Full develop/mask data stays in Lightroom.
        changed = not prior or oldmeta.get('_sync_key') != sync_key or oldmeta.get('_file_key') != file_key
        exact = 'settings' in meta
        rev = str(meta.get('revision', '')) if exact else (prior['revision'] if prior and not changed else '')
        status = 'pending' if changed else prior['status']
        values = (aid, catalog_uid, lr_id, meta.get('master_lr_id'), meta.get('copy_name', ''), int(virtual),
                  meta.get('capture_time', oldmeta.get('capture_time')), meta.get('cameraModel', meta.get('Model', '')),
                  meta.get('lens', meta.get('LensModel', '')), rating, dumps(keywords), dumps(merged), rev,
                  meta.get('availability', 'original' if size is not None else 'missing'), status, stamp, stamp)
        if prior:
            uid, pid = prior['uid'], prior['id']
            c.execute('UPDATE photos SET asset_id=?,catalog_uid=?,lr_id=?,master_lr_id=?,copy_name=?,is_virtual=?,capture_time=?,camera=?,lens=?,rating=?,keywords=?,metadata=?,revision=?,availability=?,status=?,updated_at=?,seen_at=?,deleted_at=NULL WHERE id=?', (*values, pid))
        else:
            uid = new_uid('p')
            pid = c.execute('INSERT INTO photos(asset_id,catalog_uid,lr_id,master_lr_id,copy_name,is_virtual,capture_time,camera,lens,rating,keywords,metadata,revision,availability,status,updated_at,seen_at,uid,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (*values, uid, stamp)).lastrowid
        c.execute('DELETE FROM photo_fts WHERE rowid=?', (pid,))
        c.execute('INSERT INTO photo_fts(rowid,filename,keywords,caption,camera,lens,location) VALUES(?,?,?,?,?,?,?)',
                  (pid, p.name, ' '.join(keywords), str(meta.get('caption', meta.get('Description', '')) or ''), values[7], values[8],
                   dumps(meta.get('location', meta.get('gps', {})))))
    return {'id': pid, 'uid': uid, 'asset_id': aid, 'changed': changed}


def iter_photos(root: Path):
    root = root.expanduser().resolve()
    if root.is_file():
        if root.suffix.lower() in PHOTO_EXTENSIONS:
            yield root
        return
    if not root.is_dir():
        raise ValueError('Photo folder does not exist on this computer')
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if not d.startswith('.') and not d.endswith(('.lrdata', '.lrcat-data')) and d not in {'@eaDir', '#recycle', '$RECYCLE.BIN'})
        for name in sorted(files):
            p = Path(folder) / name
            if not name.startswith('.') and p.suffix.lower() in PHOTO_EXTENSIONS:
                yield p


def ingest_file(db: Database, path: Path, source_id: int | None = None) -> dict:
    stat_key = fingerprint(path)
    prior = db.q1('SELECT p.id,p.uid,p.asset_id,p.metadata,p.catalog_uid FROM photos p JOIN assets a ON a.id=p.asset_id WHERE a.path=? AND (p.catalog_uid IS NULL OR p.is_virtual=0) ORDER BY p.catalog_uid IS NULL DESC LIMIT 1', (os.path.normcase(str(path.resolve())),))
    if prior and loads(prior['metadata'], {}).get('_file_key') == stat_key:
        db.x("UPDATE photos SET seen_at=?,deleted_at=NULL,availability='original' WHERE id=?", (now(), prior['id']))
        return {'id': prior['id'], 'uid': prior['uid'], 'asset_id': prior['asset_id'], 'changed': False}
    if prior and prior['catalog_uid']:
        return register(db, str(path), loads(prior['metadata']), catalog_uid=prior['catalog_uid'], source_id=source_id)
    return register(db, str(path), metadata(path), source_id=source_id)


def input_key(photo: dict, model_state: str) -> str:
    meta = loads(photo['metadata'], {})
    text = dumps([meta.get('_file_key'), meta.get('_sync_key'), photo['revision'], 'photo-analysis-v1', model_state])
    return hashlib.sha256(text.encode()).hexdigest()
