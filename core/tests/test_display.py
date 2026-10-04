"""Display conversion: every colour description FFmpeg reports is accepted by the zscale chain, and the
proxy for 10-bit 4:2:2 HDR / interlaced / alpha / RGB sources is browser-ready SDR BT.709."""
import itertools
import json
import subprocess

import numpy as np
import pytest

from metachlorian.media import ffmpeg as F


def _run_filter(vf: str, pix: str, size="64x36") -> np.ndarray:
    p = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=1:duration=1", "-vf",
                        f"format={pix},{vf}", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    assert p.returncode == 0, p.stderr.decode()[-500:]
    return np.frombuffer(p.stdout, np.uint8)


@pytest.mark.parametrize("prim,trc,space", list(itertools.product(
    sorted(F._PRIM) + [None, "reserved"], ["bt709", "smpte2084", "arib-std-b67", "gamma22", "bt1361e", "smpte428", None],
    ["bt709", "bt2020nc", "smpte170m", None])))
def test_every_colour_description_converts(prim, trc, space):
    tech = {"pix_fmt": "yuv420p10le", "height": 36, "color_primaries": prim, "color_transfer": trc, "color_space": space}
    out = _run_filter(F.display_filter(tech, 36), "yuv420p10le")
    assert out.size == 64 * 36 * 3


@pytest.mark.parametrize("pix", ["yuv420p", "yuvj422p", "yuv422p10le", "yuv444p12le", "yuva444p12le", "gbrp12le", "gbrp16le",
                                 "rgb48le", "gbrpf32le", "gray", "gray10le", "nv12", "p010le", "yuv420p16le"])
def test_every_pixel_format_converts(pix):
    out = _run_filter(F.display_filter({"pix_fmt": pix, "height": 36, "interlaced": True}, 36), pix)
    assert out.size == 64 * 36 * 3 and out.mean() > 30


def test_sd_and_hd_defaults_and_hdr_peak():
    sd = F.display_filter({"pix_fmt": "yuv420p", "height": 576}, 540)
    assert "color_primaries=bt470bg" in sd and "colorspace=smpte170m" in sd
    hd = F.display_filter({"pix_fmt": "yuvj422p", "height": 1080}, 540)
    assert "colorspace=smpte170m" in hd and "range=pc" in hd           # MJPEG is BT.601 full range
    assert "color_primaries=bt2020" in F.display_filter({"pix_fmt": "yuv420p10le", "height": 2160, "color_transfer": "arib-std-b67"})
    hdr = F.display_filter({"pix_fmt": "yuv422p10le", "height": 2160, "color_transfer": "smpte2084", "max_luminance": 4000}, 540)
    assert "tonemap=mobius" in hdr and "peak=19.704" in hdr            # 4000 / 203 nits


def test_proxy_of_a6700_style_hlg_10bit_422_is_sdr_bt709(tmp_path):
    src = tmp_path / "C0001.MP4"
    pre = "scale=out_color_matrix=bt709:out_range=tv,format=yuv444p10le,setparams=colorspace=bt709:color_trc=bt709:color_primaries=bt709:range=tv"
    hlg = pre + ",zscale=t=linear,format=gbrpf32le,zscale=p=2020,zscale=t=arib-std-b67:m=2020_ncl:r=tv:npl=203,format=yuv422p10le"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2", "-vf", hlg, "-c:v", "libx265",
                    "-x265-params", "log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc", str(src)], check=True)
    tech = F.technical_metadata(src)
    assert tech["bit_depth"] == 10 and tech["chroma"] == "4:2:2" and tech["hdr_format"] == "HLG"
    out = F.make_proxy(src, tmp_path / "proxy.mp4", 360, tech=tech, src_fps=25)
    assert out == {"colour": "hdr_tonemapped", "decode_errors": 0, "fallback_reason": None}
    st = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=codec_name,pix_fmt,color_transfer,color_primaries,color_space", "-of", "json",
                                    str(tmp_path / "proxy.mp4")], capture_output=True, text=True).stdout)["streams"][0]
    assert st == {"codec_name": "h264", "pix_fmt": "yuv420p", "color_space": "bt709", "color_transfer": "bt709", "color_primaries": "bt709"}
    ref = F.frame_at(tmp_path / "proxy.mp4", 1.0, 320).astype(float)
    true = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2", "-ss", "1",
                                         "-frames:v", "1", "-vf", "scale=320:180", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                        capture_output=True).stdout, np.uint8).reshape(180, 320, 3).astype(float)
    assert np.abs(ref - true).mean() < 20          # was ~75 levels off before tone mapping


def test_damaged_files_are_reported(tmp_path):
    good = tmp_path / "a.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=3", "-c:v", "libx264", "-g", "250",
                    str(good)], check=True)
    data = bytearray(good.read_bytes())
    for k in range(len(data) // 3, len(data) // 3 + 4000, 7):  # scribble over part of the stream
        data[k] = 0xFF
    bad = tmp_path / "b.mp4"
    bad.write_bytes(bytes(data))
    out = F.make_proxy(bad, tmp_path / "p.mp4", 180, tech=F.technical_metadata(bad), src_fps=25)
    assert out["decode_errors"] > 0
