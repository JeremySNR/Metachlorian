#!/usr/bin/env python3
"""Reproducible photo scale measurements and separately supplied human judgements.

The scale fixture has synthetic metadata/vectors. It measures storage/retrieval,
not photographic quality, encoder speed, ingestion speed or Lightroom latency.
Run with core/.venv/bin/python eval/photo_benchmark.py --help from the repository.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'core'))


def scale(count: int) -> dict:
    import numpy as np
    from metachlorian.config import load_settings
    from metachlorian.db import Database, dumps
    from metachlorian.photos.search import PhotoSearch

    with tempfile.TemporaryDirectory(prefix='metachlorian-photo-benchmark-') as directory:
        settings = load_settings(Path(directory), photos_enabled=True)
        settings.ensure_dirs()
        db = Database(settings.db_path)
        rng = np.random.default_rng(1907)
        started = time.perf_counter()
        evidence = dumps({'version': 1, 'provenance': {'source': 'smart_preview', 'native_resolution': False, 'colour_space': 'sRGB'},
            'global_sharpness': {'gradient_energy': .012, 'laplacian_variance': .003, 'pixels': [1024, 683]},
            'uncertainty': ['Synthetic fixture; not evidence of photographic quality.'],
            'faces': [{'box': [.1,.1,.3,.4], 'eyes_open': None, 'sharpness': {'gradient_energy': .04}}]*3})
        metadata = dumps({'cameraModel': 'Fixture Camera', 'lens': '50 mm', 'aperture': 'f/2', 'shutterSpeed': '1/250', 'isoSpeedRating': '800',
            'keywords': ['family','travel','portrait'], 'caption': 'Family on holiday at the beach', 'dateTimeOriginal': '2026-07-12 14:00:00',
            'location': {'country': 'Portugal', 'city': 'Lisbon'}, 'dimensions': {'width': 6000, 'height': 4000},
            'stack': {'position': 1}, 'fileFormat': 'RAW', 'availability': 'smart_preview', 'copy_name': '', '_file_key': None})
        with db.tx() as c:
            for start in range(0, count, 500):
                ids = range(start+1, min(start+500, count)+1)
                c.executemany("INSERT INTO assets(id,uid,path,filename,media_kind,width,height,created_at,updated_at) VALUES(?,?,?,?, 'photo',6000,4000,1,1)",
                    ((i,f'a{i}',f'/offline/holiday/{i}.raw',f'{i}.raw') for i in ids))
                c.executemany("INSERT INTO photos(id,uid,asset_id,capture_time,camera,rating,metadata,evidence,burst_id,status,created_at,updated_at) VALUES(?,?,?,'2026-07-12T14:00:00','Fixture Camera',?,?,?,?,'ready',1,1)",
                    ((i,f'p{i}',i,i%6,metadata,evidence,f'burst-{i//4}') for i in ids))
                c.executemany('INSERT INTO photo_fts(rowid,filename,keywords,caption,camera,lens,location) VALUES(?,?,?,?,?,?,?)',
                    ((i,f'{i}.raw','family travel portrait',f'Family on holiday set {i%20}','Fixture Camera','50 mm','Lisbon') for i in ids))
                vectors = rng.normal(size=(len(ids),768)).astype(np.float32)
                vectors /= np.linalg.norm(vectors,axis=1,keepdims=True)
                c.executemany("INSERT INTO photo_vectors(photo_id,model,dim,vec,updated_at) VALUES(?,'siglip-base-multilingual',768,?,1)",
                    ((i,v.astype(np.float16).tobytes()) for i,v in zip(ids,vectors)))
                # Three face observations per image, with no persistent crops.
                embedding = np.ones(128, np.float16).tobytes()
                c.executemany('INSERT INTO photo_faces(photo_id,box,score,size_px,embedding,evidence) VALUES(?,?,.95,120,?,?)',
                    ((i,'[0.1,0.1,0.3,0.4]',embedding,'{"eyes_open":null,"native_resolution":false}') for i in ids for _ in range(3)))
        population = time.perf_counter()-started
        db.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        storage = settings.db_path.stat().st_size
        search = PhotoSearch(db,settings)
        times = []
        for _ in range(10):
            t = time.perf_counter(); search.search(filters={'min_rating': 3}); times.append((time.perf_counter()-t)*1000)
        query = rng.normal(size=768).astype(np.float32); query /= np.linalg.norm(query)
        # Isolate actual ANN + SQL + fusion latency from model inference.
        with patch('metachlorian.photos.search.models.installed',return_value=True), patch('metachlorian.media.siglip.text_vector',return_value=query):
            t = time.perf_counter(); search.search('family holiday'); cold = (time.perf_counter()-t)*1000
            ann = []
            for _ in range(10):
                t = time.perf_counter(); search.search('family holiday'); ann.append((time.perf_counter()-t)*1000)
            restarted = PhotoSearch(db, settings)
            t = time.perf_counter(); restarted.search('family holiday'); reopened = (time.perf_counter()-t)*1000
        vector_cache = sum(path.stat().st_size for path in (settings.data_dir/'photo-index').glob('*'))
        storage += vector_cache
        report = {'fixture': 'synthetic metadata, 768-dimensional vectors and three faces per photo; no original files',
            'platform': platform.platform(), 'photo_count': count, 'persistent_index_bytes': storage,
            'index_target_bytes': 2*1024**3, 'index_within_target': storage <= 2*1024**3,
            'vector_cache_bytes': vector_cache, 'database_bytes': settings.db_path.stat().st_size,
            'model_bytes': 'excluded; shared existing photo pack is approximately 947 MB',
            'temporary_cache': '256 MiB configured limit, tested separately; no previews generated in this benchmark',
            'fixture_population_seconds': round(population,2), 'metadata_search_p95_ms': round(float(np.percentile(times,95)),2),
            'hybrid_cold_ms': round(cold,2), 'hybrid_warm_p95_ms': round(float(np.percentile(ann,95)),2),
            'hybrid_reopened_ms': round(reopened,2),
            'exclusions': ['encoder inference','real catalogue synchronisation','Lightroom rendering','image quality','disk cache under real browsing']}
        db.close()
        return report


def preferences(path: Path) -> dict:
    rows = json.loads(path.read_text())
    seen, grouped = set(), {}
    for row in rows:
        if row['event_id'] in seen:
            raise ValueError('Use one independently sampled comparison per event to avoid burst leakage')
        seen.add(row['event_id'])
        if row['category'] not in {'portrait','travel','family'} or row['preferred'] not in {'baseline','candidate','tie'} or row.get('blind') is not True:
            raise ValueError('Each blind judgement needs category, preferred and event_id')
        grouped.setdefault(row['category'],[]).append(row)
    result = {}
    for category, votes in grouped.items():
        decisive = [v for v in votes if v['preferred'] != 'tie']
        n, wins = len(decisive), sum(v['preferred']=='candidate' for v in decisive)
        lower = 0.
        if n:
            z, p = 1.96, wins/n
            lower = (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n)
        regressions = sum(v.get('severe_regression',False) for v in votes)
        result[category] = {'comparisons': len(votes), 'decisive': n, 'candidate_wins': wins,
            'ties': len(votes)-n, 'wilson_95_lower': round(lower,4), 'severe_regressions': regressions,
            'passes': len(votes)>=30 and lower>.5 and regressions==0}
    return {'categories': result, 'promote': set(result)=={'portrait','travel','family'} and all(v['passes'] for v in result.values()),
        'note': 'A benchmark gate, not a universal aesthetic judgement. Keep an unchanged baseline and inspect failure cases.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    large = commands.add_parser('scale'); large.add_argument('--count',type=int,default=100000)
    human = commands.add_parser('preferences'); human.add_argument('judgements',type=Path)
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    if args.command=='scale' and not 1 <= args.count <= 100000:
        parser.error('count must be 1..100000')
    result = scale(args.count) if args.command=='scale' else preferences(args.judgements)
    output = json.dumps(result,indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(output+'\n')
    print(output)
    if args.command == 'scale' and not result['index_within_target']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
