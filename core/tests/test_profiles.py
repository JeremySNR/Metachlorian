import pytest

from metachlorian.media.profiles import capture_profile


@pytest.mark.parametrize('gamma,label', [
    ('S-Log3', 'Sony S-Log3'), ('slog2', 'Sony S-Log2'),
    ('LogC4', 'ARRI LogC4'), ('ARRI Log C3', 'ARRI LogC3'),
    ('LogC', 'ARRI LogC (version unspecified)'),
    ('Canon Log 2', 'Canon C-Log2'), ('C-Log3', 'Canon C-Log3'),
    ('V-Log L', 'Panasonic V-Log L'), ('F-Log2', 'Fujifilm F-Log2'),
    ('D-Log M', 'DJI D-Log M'), ('Apple Log', 'Apple Log'),
    ('Blackmagic Film Gen 5', 'Blackmagic Film Gen 5'),
])
def test_named_capture_profiles_preserve_metadata_evidence(gamma, label):
    profile = capture_profile({'gamma': gamma})
    assert profile['log_profile_name'] == label
    assert profile['log_profile_source'] == 'metadata'
    assert profile['log_profile_evidence'] == {'field': 'gamma', 'value': gamma}


@pytest.mark.parametrize('tech', [
    {'camera_make': 'ARRI', 'camera_model': 'ALEXA'},
    {'camera_make': 'Sony', 'tags': {'comment': 'Converted from S-Log3 to Rec.709'}},
    {'color_transfer': 'arib-std-b67'}, {'color_transfer': 'smpte2084'},
    {'tags': {'comment': 'Travel vlog and catalogue'}}, {'gamma': '2.4'},
])
def test_camera_brand_comments_hdr_and_flat_appearance_do_not_confirm_profile(tech):
    profile = capture_profile(tech)
    assert profile['log_profile_name'] is None
    assert profile['log_profile_source'] is None


def test_profile_from_container_tags_is_specific():
    assert capture_profile({'tags': {'CaptureGammaEquation': 'S-Log3'}})['log_profile_name'] == 'Sony S-Log3'


def test_existing_asset_records_expose_named_profile_without_reanalysis(lib):
    from metachlorian.db import dumps
    from metachlorian.records import build_asset_doc

    _, db = lib
    db.x("INSERT INTO assets(uid,path,filename,size,mtime,quick_hash,status,created_at,updated_at,tech) "
         "VALUES('a','/a.mp4','a.mp4',1,0,'q','ready',0,0,?)", (dumps({'gamma': 'LogC4'}),))
    assert build_asset_doc(db, db.q1('SELECT id FROM assets')[0])['technical']['log_profile_name'] == 'ARRI LogC4'


def test_exiftool_keeps_named_gamma_and_gamut_and_numeric_gps(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from metachlorian.media import ffmpeg

    monkeypatch.setattr(ffmpeg.shutil, 'which', lambda name: 'exiftool')
    def run(args, **kwargs):
        assert '-n' not in args  # a global numeric flag loses named capture profiles
        assert '-GPSLatitude#' in args
        return SimpleNamespace(stdout=b'[{"CaptureGammaEquation":"S-Log3","CaptureColorPrimaries":"S-Gamut3.Cine","GPSLatitude":51.5,"GPSLongitude":-0.1}]')
    monkeypatch.setattr(ffmpeg.subprocess, 'run', run)
    tech = ffmpeg._exiftool(tmp_path / 'clip.mp4')
    assert tech['gamma'] == 'S-Log3'
    assert tech['capture_color_gamut'] == 'S-Gamut3.Cine'
    assert tech['gps']['lat'] == 51.5
