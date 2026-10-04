"""Camera raw through a configured vendor decoder, and exports that keep bit depth, chroma and HDR tags."""
import json
import shutil
import subprocess
import sys
import textwrap

from metachlorian import pipeline
from metachlorian.auth import LOCAL_ADMIN
from metachlorian.exports import package as P
from metachlorian.ingest.scan import add_source, scan_source
from metachlorian.media import ffmpeg as F
from metachlorian.service import Library

from .test_ingest_pipeline import run_all

# Stands in for REDline / ARRI Reference Tool / a Blackmagic RAW SDK tool: the "raw" file is secretly an MP4.
FAKE_DECODER = textwrap.dedent('''\
    #!{python}
    import subprocess, sys
    src, out = sys.argv[1], sys.argv[2]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuv444p10le",
                    "-c:a", "pcm_s24le", out], check=True)
''')


def _stream(path):
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "stream=codec_name,profile,pix_fmt,color_transfer,color_primaries", "-of", "json", str(path)],
                                     capture_output=True, text=True).stdout)["streams"][0]


def test_camera_raw_needs_a_decoder_then_works_through_its_master(lib, tmp_path, sample_video):
    s, db = lib
    d = tmp_path / "card"
    d.mkdir()
    shutil.copy(sample_video, d / "A001_C002.braw")
    scan_source(db, add_source(db, str(d)))
    run_all(s, db)
    a = db.q1("SELECT * FROM assets")
    run = db.q1("SELECT status, error FROM analysis_runs WHERE asset_id=? AND analyser='technical'", (a["id"],))
    assert a["status"] == "error" and run["status"] == "failed"
    assert "Blackmagic RAW" in run["error"] and "Settings → Formats" in run["error"]
    assert db.q1("SELECT attempts FROM jobs WHERE asset_id=? AND analyser='technical'", (a["id"],))["attempts"] == 1  # not retried

    tool = tmp_path / "braw-decode"
    tool.write_text(FAKE_DECODER.format(python=sys.executable))
    tool.chmod(0o755)
    s.raw_decoders = {"braw": f"{tool} {{input}} {{output}}"}
    pipeline.plan_all(db, s)  # a new decoder changes the technical step's inputs, so it runs again
    run_all(s, db)
    a = db.q1("SELECT * FROM assets")
    tech = json.loads(a["tech"])
    assert a["status"] == "ready" and a["local_path"].endswith("master/master.mov")
    assert tech["decoded_from"]["format"] == "Blackmagic RAW" and tech["bit_depth"] >= 10 and tech["chroma"] == "4:4:4"
    assert db.q1("SELECT COUNT(*) n FROM shots WHERE asset_id=? AND active=1", (a["id"],))["n"] >= 2
    shot = db.q1("SELECT uid FROM shots WHERE asset_id=? AND active=1 ORDER BY idx", (a["id"],))["uid"]
    out = Library(db, s).export_clip(LOCAL_ADMIN, shot, mode="file")
    assert out["file"].endswith(".mov") and _stream(out["file"])["codec_name"] == "prores"   # cut from the decoded master


def test_trimmed_originals_keep_depth_chroma_and_hdr(tmp_path):
    src = tmp_path / "C0001.MP4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=3", "-f", "lavfi",
                    "-i", "sine=duration=3:sample_rate=48000", "-c:v", "libx265", "-pix_fmt", "yuv422p10le", "-x265-params",
                    "log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc", "-c:a", "aac", "-shortest", str(src)], check=True)
    out = F.render_master(src, tmp_path / "clip", 0.5, 2.0)
    st = _stream(out)
    assert out.suffix == ".mov" and st["codec_name"] == "prores" and st["pix_fmt"] == "yuv422p10le"
    assert st["color_transfer"] == "arib-std-b67" and st["color_primaries"] == "bt2020"     # still HDR, untouched
    eight = tmp_path / "plain.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2", "-pix_fmt", "yuv420p",
                    str(eight)], check=True)
    out8 = F.render_master(eight, tmp_path / "clip8", 0.0, 1.0)
    assert out8.suffix == ".mp4" and _stream(out8)["codec_name"] == "h264"
    alpha = tmp_path / "gfx.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=1", "-c:v", "prores_ks",
                    "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(alpha)], check=True)
    assert _stream(F.render_master(alpha, tmp_path / "gfx_out", 0.0, 0.5))["pix_fmt"] == "yuva444p12le"     # alpha kept


def test_unreadable_files_fail_once_with_a_clear_message(lib, tmp_path):
    s, db = lib
    d = tmp_path / "junk"
    d.mkdir()
    (d / "broken.mov").write_bytes(b"\x00" * 50_000)
    scan_source(db, add_source(db, str(d)))
    run_all(s, db)
    run = db.q1("SELECT status, error FROM analysis_runs WHERE analyser='technical'")
    assert run["status"] == "failed" and "FFmpeg cannot read this file" in run["error"]
    assert db.q1("SELECT attempts FROM jobs WHERE analyser='technical'")["attempts"] == 1


def test_package_trimmed_originals_are_prores_for_10bit(lib, tmp_path):
    s, db = lib
    d = tmp_path / "a6700"
    d.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2", "-f", "lavfi", "-i",
                    "smptebars=size=640x360:rate=25:duration=2", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
                    "-c:v", "libx265", "-pix_fmt", "yuv422p10le", "-x265-params", "log-level=error", str(d / "C0001.MP4")], check=True)
    scan_source(db, add_source(db, str(d)))
    run_all(s, db)
    shot = db.q1("SELECT uid FROM shots WHERE active=1 ORDER BY idx")["uid"]
    res = P.build_package(db, s, [{"shot_uid": shot}], "a6700", media_policy="trimmed_originals", mode="stringout")
    man = json.loads((P.Path(res["path"]) / "manifest.json").read_text())
    orig = [m for m in man["media"] if m["kind"] == "trimmed_original"]
    assert orig and orig[0]["file"].endswith(".mov") and orig[0]["video_codec"] == "prores"
