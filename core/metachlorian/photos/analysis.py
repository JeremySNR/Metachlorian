"""Measured evidence, not a universal beauty score. All inference is local."""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .. import models
from ..db import dumps, loads, now
from ..media.faceid import iou

_MODEL_LOCK = threading.RLock()


@lru_cache(maxsize=4)
def _face_detector(root: str):
    return cv2.FaceDetectorYN.create(str(models.model_dir(Path(root), 'yunet') / models.SPECS['yunet'].files[0]), '', (1024,1024), .8, .3, 5000)


@lru_cache(maxsize=4)
def _face_recognizer(root: str):
    return cv2.FaceRecognizerSF.create(str(models.model_dir(Path(root), 'sface') / models.SPECS['sface'].files[0]), '')


def sharpness(rgb: np.ndarray) -> dict:
    if min(rgb.shape[:2]) < 12:
        return {'available': False, 'reason': 'Region has too few pixels'}
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    smooth = cv2.GaussianBlur(gray, (3, 3), .7)
    gx, gy = cv2.Sobel(smooth, cv2.CV_32F, 1, 0), cv2.Sobel(smooth, cv2.CV_32F, 0, 1)
    energy = float(np.mean(gx*gx + gy*gy))
    return {'available': True, 'gradient_energy': round(energy, 6),
            'laplacian_variance': round(float(cv2.Laplacian(smooth, cv2.CV_32F).var()), 6),
            'contrast': round(float(gray.std()), 5), 'pixels': [rgb.shape[1], rgb.shape[0]],
            'interpretation': 'Compare similarly framed regions at the same scale; texture and noise also affect these measurements.'}


def measure(im: Image.Image, provenance: dict) -> dict:
    rgb = np.asarray(im.convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(small)[:8, :8]
    bits = dct > np.median(dct.flatten()[1:])
    phash = ''.join(f'{n:02x}' for n in np.packbits(bits))
    w, h = im.size
    border = np.concatenate((gray[:max(1, h//20), :].ravel(), gray[-max(1, h//20):, :].ravel(), gray[:, :max(1, w//20)].ravel(), gray[:, -max(1, w//20):].ravel()))
    edges = cv2.Canny(gray, 80, 160)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, max(30, w//8), minLineLength=max(30, w//4), maxLineGap=20)
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4) if lines is not None else []:
        angle = float(np.degrees(np.arctan2(y2-y1, x2-x1)))
        if abs(angle) < 15:
            angles.append(angle)
    return {'version': 1, 'provenance': provenance, 'width': w, 'height': h, 'phash': phash,
            'global_sharpness': sharpness(rgb),
            'exposure': {'render_highlights_fraction': float(np.mean(np.max(rgb, axis=2) >= 253)),
                         'render_shadows_fraction': float(np.mean(np.max(rgb, axis=2) <= 3)),
                         'luminance_percentiles': [float(x) for x in np.percentile(gray, [1, 10, 50, 90, 99])],
                         'raw_recovery_known': False},
            'composition': {'aspect_ratio': w/h, 'bright_border_fraction': float(np.mean(border > 245)),
                            'horizontal_line_angles': angles[:8], 'horizon_confirmed': False},
            'uncertainty': ['Expression and composition need visual comparison.',
                            'Rendered clipping is not evidence of unrecoverable RAW data.'] + ([] if provenance.get('native_resolution') else ['Original-resolution focus has not been checked.'])}


def analyse(im: Image.Image, settings, provenance: dict) -> tuple[dict, np.ndarray | None, list[dict]]:
    evidence = measure(im, provenance)
    rgb = np.asarray(im.convert('RGB'))
    vector, faces = None, []
    available = lambda name: models.installed(settings.resolved_models_dir, name)
    evidence['models'] = {}
    with _MODEL_LOCK:
        if available('siglip-base-multilingual'):
            from ..media.siglip import load
            vector = load(str(settings.resolved_models_dir)).encode_images([rgb])[0]
            evidence['models']['semantic'] = 'siglip-base-multilingual'
        else:
            evidence['models']['semantic'] = 'unavailable: install the visual model pack'
        if available('yunet'):
            detector = _face_detector(str(settings.resolved_models_dir))
            detector.setInputSize((im.width, im.height))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            _, detected = detector.detect(bgr)
            recognizer = None
            if settings.face_identity and available('sface'):
                recognizer = _face_recognizer(str(settings.resolved_models_dir))
            for face in detected if detected is not None else []:
                x, y, w, h = face[:4]
                if min(w, h) < 20:
                    continue
                box = [max(0., float(x/im.width)), max(0., float(y/im.height)), min(1., float((x+w)/im.width)), min(1., float((y+h)/im.height))]
                crop = rgb[max(0, int(y)):min(im.height, int(y+h)), max(0, int(x)):min(im.width, int(x+w))]
                eyes = []
                for ex, ey in (face[4:6], face[6:8]):
                    half = max(3, int(w*.13))
                    eyes.append(sharpness(rgb[max(0, int(ey)-half):min(im.height, int(ey)+half), max(0, int(ex)-half):min(im.width, int(ex)+half)]))
                emb = None
                if recognizer and min(w, h) >= 40:
                    aligned = recognizer.alignCrop(bgr, face)
                    emb = recognizer.feature(aligned).reshape(-1).astype(np.float32)
                    emb /= np.linalg.norm(emb) + 1e-8
                faces.append({'box': box, 'score': float(face[-1]), 'size_px': int(min(w, h)), 'embedding': emb,
                              'evidence': {'sharpness': sharpness(crop), 'eyes': eyes, 'eyes_open': None,
                                           'expression': 'unknown', 'native_resolution': provenance.get('native_resolution', False)}})
            evidence['models']['face_detection'] = 'yunet'
        else:
            evidence['models']['face_detection'] = 'unavailable'
        _landmarks(rgb, faces, settings, evidence)
    evidence['faces'] = [{k: v for k, v in f.items() if k != 'embedding'} for f in faces]
    evidence['crop_candidates'] = crop_candidates(im.width, im.height, faces)
    return evidence, vector, faces


def _landmarks(rgb, faces, settings, evidence):
    if not models.installed(settings.resolved_models_dir, 'face-landmarker'):
        evidence['models']['landmarks'] = 'unavailable'
        return
    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        options = vision.FaceLandmarkerOptions(base_options=python.BaseOptions(model_asset_path=str(models.model_dir(settings.resolved_models_dir, 'face-landmarker') / 'face_landmarker.task')), num_faces=16, output_face_blendshapes=True)
        with vision.FaceLandmarker.create_from_options(options) as detector:
            result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
        for landmarks, blends in zip(result.face_landmarks, result.face_blendshapes):
            box = [min(p.x for p in landmarks), min(p.y for p in landmarks), max(p.x for p in landmarks), max(p.y for p in landmarks)]
            matches = sorted(((iou(f['box'], box), i) for i, f in enumerate(faces)), reverse=True)
            if matches and matches[0][0] >= .3:
                face = faces[matches[0][1]]
                values = {b.category_name: b.score for b in blends}
                face['evidence']['eye_blink_coefficients'] = [values.get('eyeBlinkLeft'), values.get('eyeBlinkRight')]
                face['evidence']['mouth_smile_coefficients'] = [values.get('mouthSmileLeft'), values.get('mouthSmileRight')]
                face['evidence']['landmark_note'] = 'Expression coefficients are evidence, not emotion labels or calibrated blink probabilities; verify toddlers, pose and occlusion visually.'
        evidence['models']['landmarks'] = 'mediapipe-face-landmarker-v1'
    except (ImportError, RuntimeError, ValueError) as exc:
        evidence['models']['landmarks'] = 'unavailable: ' + str(exc)[:200]


def crop_candidates(width: int, height: int, faces: list[dict]) -> list[dict]:
    candidates = [{'box': [0, 0, 1, 1], 'reason': 'Preserve the complete frame'}]
    if not faces:
        return candidates
    left, top = min(f['box'][0] for f in faces), min(f['box'][1] for f in faces)
    right, bottom = max(f['box'][2] for f in faces), max(f['box'][3] for f in faces)
    # Generous breathing room, including below faces for gesture/body context.
    box = [max(0, left-.15), max(0, top-.15), min(1, right+.15), min(1, bottom+.3)]
    retained = (box[2]-box[0])*(box[3]-box[1])
    if .5 <= retained < .95:
        candidates.append({'box': box, 'retained_fraction': retained, 'reason': 'Possible closer framing; inspect hands, gesture and surroundings before applying'})
    return candidates


def save_faces(db, photo_id: int, faces: list[dict]):
    with db.tx() as c:
        # Retain human labels even when a temporary crop hides the face. They
        # can be reattached when that region is visible again, without crops.
        c.execute("INSERT INTO photo_face_labels(photo_id,identity_id,box,embedding,assigned_by) SELECT photo_id,identity_id,box,embedding,assigned_by FROM photo_faces WHERE photo_id=? AND assigned_by IN ('human','named') AND identity_id IS NOT NULL AND embedding IS NOT NULL ON CONFLICT(photo_id,identity_id) DO UPDATE SET box=excluded.box,embedding=excluded.embedding,assigned_by=excluded.assigned_by", (photo_id,))
        old = [dict(r) for r in c.execute('SELECT * FROM photo_face_labels WHERE photo_id=?', (photo_id,))]
        c.execute('DELETE FROM photo_faces WHERE photo_id=?', (photo_id,))
        identities = [dict(r) for r in c.execute('SELECT id,centroid FROM identities')]
        for f in faces:
            emb = f.get('embedding')
            person, by = None, 'auto'
            for prior in old:
                same = float(np.frombuffer(prior['embedding'], np.float16).astype(np.float32) @ emb) if prior['embedding'] and emb is not None else -1
                if not prior.get('used') and (same >= .7 or (same >= .5 and iou(loads(prior['box']), f['box']) >= .4)):
                    person, by = prior['identity_id'], prior['assigned_by']
                    prior['used'] = True
                    break
            if person is None and emb is not None:
                sims = [(float(np.frombuffer(p['centroid'], np.float32) @ emb), p['id']) for p in identities]
                if sims and max(sims)[0] >= .55:
                    person = max(sims)[1]
                else:
                    person = c.execute('INSERT INTO identities(centroid,n,created_at,updated_at) VALUES(?,1,?,?)', (emb.astype(np.float32).tobytes(), now(), now())).lastrowid
                    identities.append({'id': person, 'centroid': emb.astype(np.float32).tobytes()})
            c.execute('INSERT INTO photo_faces(photo_id,box,score,size_px,embedding,identity_id,assigned_by,evidence) VALUES(?,?,?,?,?,?,?,?)',
                      (photo_id, dumps(f['box']), f['score'], f['size_px'], emb.astype(np.float16).tobytes() if emb is not None else None, person, by, dumps(f['evidence'])))


def assign_burst(db, photo: dict, phash: str):
    capture = photo.get('capture_time')
    if not capture:
        return
    try:
        when = datetime.fromisoformat(capture.replace('Z', '+00:00'))
    except ValueError:
        return
    lo, hi = (when-timedelta(seconds=3)).isoformat(), (when+timedelta(seconds=3)).isoformat()
    rows = db.q('SELECT p.id,p.uid,p.burst_id,p.phash FROM photos p WHERE p.capture_time BETWEEN ? AND ? AND p.id<>? AND p.camera=? AND p.catalog_uid IS ? AND p.phash IS NOT NULL ORDER BY p.id',
                (lo, hi, photo['id'], photo.get('camera', ''), photo.get('catalog_uid')))
    for other in rows:
        distance = (int(other['phash'], 16) ^ int(phash, 16)).bit_count()
        if distance <= 12:
            burst = other['burst_id'] or 'b' + hashlib.sha256(other['uid'].encode()).hexdigest()[:20]
            db.x('UPDATE photos SET burst_id=? WHERE id IN (?,?)', (burst, photo['id'], other['id']))
            break
