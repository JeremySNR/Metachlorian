import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageCms

from metachlorian.photos import analysis, images, store
from .test_photos import photos


def test_profile_conversion_and_16_bit_tiff(tmp_path):
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    path = tmp_path/'profile.png'
    Image.new('RGB', (80,40), (70,110,180)).save(path, icc_profile=profile)
    im, info = images.decode(path)
    assert im.getpixel((5,5)) == (70,110,180) and info['colour_space'] == 'sRGB'
    path = tmp_path/'gray.tiff'
    Image.fromarray(np.full((40,80), 32768, dtype=np.uint16)).save(path)
    im, _ = images.decode(path)
    assert im.getpixel((5,5)) == (128,128,128)


def test_raw_embedded_orientation_and_native_decode_are_distinct(tmp_path, monkeypatch):
    path = tmp_path/'photo.raw'; path.write_bytes(b'fixture')
    # Use .dng so the production RAW adapter chooses LibRaw.
    path = path.rename(path.with_suffix('.dng'))
    buffer = io.BytesIO(); Image.new('RGB',(80,40),(130,80,30)).save(buffer,'JPEG')
    class Raw:
        sizes = SimpleNamespace(flip=6)
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def extract_thumb(self): return SimpleNamespace(format=1,data=buffer.getvalue())
        def postprocess(self, **kwargs):
            assert kwargs['use_camera_wb'] and not kwargs['half_size']
            return np.zeros((80,40,3),np.uint8)  # LibRaw already oriented this.
    import rawpy
    monkeypatch.setattr(rawpy,'imread',lambda _: Raw())
    monkeypatch.setattr(rawpy,'ThumbFormat',SimpleNamespace(JPEG=1))
    im, info = images.decode(path)
    assert im.size == (40,80) and info['source'] == 'embedded_preview'
    im, info = images.decode(path, native=True)
    assert im.size == (40,80) and info['native_resolution']


def test_local_face_measurements_report_uncertainty(photos, monkeypatch):
    service, _, _ = photos
    class Detector:
        def setInputSize(self,size): assert size == (160,120)
        def detect(self,bgr): return None, np.array([[30,20,60,70,45,45,70,45,60,60,45,70,70,70,.99]],np.float32)
    class Recognizer:
        def alignCrop(self,bgr,face): return bgr
        def feature(self,_): return np.ones(128,np.float32)
    monkeypatch.setattr(analysis,'_face_detector',lambda _: Detector())
    monkeypatch.setattr(analysis,'_face_recognizer',lambda _: Recognizer())
    monkeypatch.setattr(analysis.models,'installed',lambda _,name: name in {'yunet','sface'})
    evidence, vector, faces = analysis.analyse(Image.new('RGB',(160,120),(120,80,60)),service.settings,{'native_resolution':False})
    assert vector is None and len(faces) == 1
    assert faces[0]['evidence']['eyes_open'] is None
    assert len(faces[0]['evidence']['eyes']) == 2
    assert np.isclose(np.linalg.norm(faces[0]['embedding']),1)
    assert not faces[0]['evidence']['native_resolution']
    assert evidence['crop_candidates'][0]['box'] == [0,0,1,1]


def test_rescanning_a_linked_lightroom_file_keeps_one_master(photos):
    service, bridge, uid = photos
    path = __import__('pathlib').Path(bridge.photos['1']['path'])
    assert store.ingest_file(service.db,path)['uid'] == uid
    Image.new('RGB',(120,80),(50,100,150)).save(path)
    assert store.ingest_file(service.db,path)['uid'] == uid
    assert service.db.q1('SELECT COUNT(*) FROM photos')[0] == 1
