import os

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from metachlorian.ingest.scan import add_source, scan_source  # noqa: E402


def test_s3_source_ingest_and_dedupe(lib, sample_video, monkeypatch):
    s, db = lib
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with moto.mock_aws():
        c = boto3.client("s3", region_name="us-east-1")
        c.create_bucket(Bucket="footage")
        c.upload_file(str(sample_video), "footage", "trips/lisbon/clip.mp4")
        c.upload_file(str(sample_video), "footage", "trips/lisbon/same-bytes.mp4")
        c.put_object(Bucket="footage", Key="trips/readme.txt", Body=b"not a video")
        sid = add_source(db, "s3://footage/trips")
        r = scan_source(db, sid, s.data_dir / "cache" / "s3")
        assert r.added == 1 and r.duplicates == 1
        a = db.q1("SELECT path, local_path, filename FROM assets")
        assert a["path"] == "s3://footage/trips/lisbon/clip.mp4" and a["filename"] == "clip.mp4"
        assert a["local_path"] and os.path.exists(a["local_path"])
        r = scan_source(db, sid, s.data_dir / "cache" / "s3")
        assert r.unchanged == 2
