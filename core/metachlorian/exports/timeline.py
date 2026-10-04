"""Timeline interchange: OpenTimelineIO (.otio), FCPXML 1.10 and CMX 3600 EDL.

All three are written from one simple sequence model so they always agree.
OTIO is written with the official library; FCPXML and EDL with small writers
of our own (see docs/decisions/012-interchange-and-cutawan-handoff.md).
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


@dataclass
class Clip:
    name: str
    reel: str
    media_path: str          # path as it should appear in the timeline (relative or absolute)
    media_duration: float    # seconds, of the media file
    src_in: float            # media clock
    src_out: float
    record_in: float         # sequence clock
    track: int = 1           # 1 = V1 (A-roll / main), 2 = V2 (inserts)
    has_audio: bool = True
    asset_offset: float = 0.0   # asset time of media frame 0 (for source timecode)
    asset_rate: Fraction = Fraction(25)
    width: int = 1920
    height: int = 1080
    note: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.src_out - self.src_in)


@dataclass
class Sequence:
    name: str
    rate: Fraction
    width: int
    height: int
    clips: list[Clip] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max((c.record_in + c.duration for c in self.clips), default=0.0)


def rate_of(fps: float | None) -> Fraction:
    """Snap a measured fps to the nearest standard rational rate."""
    if not fps:
        return Fraction(25)
    std = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30), Fraction(48), Fraction(50),
           Fraction(60000, 1001), Fraction(60), Fraction(120)]
    best = min(std, key=lambda r: abs(float(r) - fps))
    return best if abs(float(best) - fps) < 0.05 * fps else Fraction(fps).limit_denominator(1001)


def frames(seconds: float, rate: Fraction) -> int:
    return int(round(seconds * float(rate)))


def timecode(seconds: float, rate: Fraction) -> str:
    fps = int(round(float(rate)))
    drop = rate.denominator == 1001 and fps in (30, 60)
    f = frames(seconds, rate)
    if drop:
        d = 2 if fps == 30 else 4
        per10 = fps * 600 - d * 9
        per1 = fps * 60 - d
        tens, rem = divmod(f, per10)
        f += d * 9 * tens + (d * ((rem - d) // per1) if rem > d else 0)
    h, rem = divmod(f, fps * 3600)
    m, rem = divmod(rem, fps * 60)
    s, fr = divmod(rem, fps)
    sep = ";" if drop else ":"
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{fr:02d}"


# ---------------------------------------------------------------- OTIO

def write_otio(seq: Sequence, path: Path) -> None:
    import opentimelineio as otio

    rate = float(seq.rate)
    tl = otio.schema.Timeline(name=seq.name)
    tl.global_start_time = otio.opentime.RationalTime(0, rate)
    for tno in sorted({c.track for c in seq.clips}):
        track = otio.schema.Track(name=f"V{tno}", kind=otio.schema.TrackKind.Video)
        cursor = 0.0
        for c in sorted((c for c in seq.clips if c.track == tno), key=lambda c: c.record_in):
            if c.record_in > cursor + 1e-6:
                track.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(0, rate), otio.opentime.RationalTime(frames(c.record_in - cursor, seq.rate), rate))))
            ref = otio.schema.ExternalReference(target_url=c.media_path, available_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, rate), otio.opentime.RationalTime(frames(c.media_duration, seq.rate), rate)))
            clip = otio.schema.Clip(name=c.name, media_reference=ref, source_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(frames(c.src_in, seq.rate), rate), otio.opentime.RationalTime(frames(c.duration, seq.rate), rate)))
            clip.metadata["metachlorian"] = {"reel": c.reel, "asset_offset": c.asset_offset, "note": c.note}
            track.append(clip)
            cursor = c.record_in + c.duration
        tl.tracks.append(track)
    a_clips = [c for c in seq.clips if c.track == 1 and c.has_audio]
    if a_clips:
        at = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
        cursor = 0.0
        for c in sorted(a_clips, key=lambda c: c.record_in):
            if c.record_in > cursor + 1e-6:
                at.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(0, rate), otio.opentime.RationalTime(frames(c.record_in - cursor, seq.rate), rate))))
            ref = otio.schema.ExternalReference(target_url=c.media_path)
            at.append(otio.schema.Clip(name=c.name, media_reference=ref, source_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(frames(c.src_in, seq.rate), rate), otio.opentime.RationalTime(frames(c.duration, seq.rate), rate))))
            cursor = c.record_in + c.duration
        tl.tracks.append(at)
    otio.adapters.write_to_file(tl, str(path))


# ---------------------------------------------------------------- FCPXML 1.10

def _rt(seconds: float, rate: Fraction) -> str:
    """Rational time on frame boundaries: frames * frameDuration."""
    fr = frames(seconds, rate)
    t = Fraction(fr) * Fraction(rate.denominator, rate.numerator)
    return "0s" if t == 0 else f"{t.numerator}/{t.denominator}s" if t.denominator != 1 else f"{t.numerator}s"


def write_fcpxml(seq: Sequence, path: Path, base_dir: Path | None = None) -> None:
    rate = seq.rate
    fd = f"{rate.denominator}/{rate.numerator}s"
    root = ET.Element("fcpxml", version="1.10")
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r0", name=f"FFVideoFormat{seq.height}p{round(float(rate) * 100) / 100:g}", frameDuration=fd,
                  width=str(seq.width), height=str(seq.height))
    assets: dict[str, str] = {}
    for c in seq.clips:
        if c.media_path in assets:
            continue
        aid = f"r{len(assets) + 1}"
        assets[c.media_path] = aid
        a = ET.SubElement(res, "asset", id=aid, name=Path(c.media_path).stem, start="0s", duration=_rt(c.media_duration, rate),
                          hasVideo="1", hasAudio="1" if c.has_audio else "0", format="r0")
        url = c.media_path if "://" in c.media_path else (Path(c.media_path).as_posix() if not Path(c.media_path).is_absolute()
                                                           else Path(c.media_path).as_uri())
        ET.SubElement(a, "media-rep", kind="original-media", src=url)
    lib = ET.SubElement(root, "library")
    ev = ET.SubElement(lib, "event", name="Metachlorian")
    proj = ET.SubElement(ev, "project", name=seq.name)
    sq = ET.SubElement(proj, "sequence", format="r0", duration=_rt(seq.duration, rate), tcStart="0s", tcFormat="NDF", audioLayout="stereo",
                       audioRate="48k")
    spine = ET.SubElement(sq, "spine")
    main = sorted((c for c in seq.clips if c.track == 1), key=lambda c: c.record_in)
    inserts = sorted((c for c in seq.clips if c.track != 1), key=lambda c: c.record_in)
    cursor = 0.0
    elements = []
    for c in main:
        if c.record_in > cursor + 1e-6:
            g = ET.SubElement(spine, "gap", name="Gap", offset=_rt(cursor, rate), start="0s", duration=_rt(c.record_in - cursor, rate))
            elements.append((cursor, c.record_in, g))
        el = ET.SubElement(spine, "asset-clip", ref=assets[c.media_path], name=c.name, offset=_rt(c.record_in, rate),
                           start=_rt(c.src_in, rate), duration=_rt(c.duration, rate), format="r0", tcFormat="NDF")
        if c.note:
            ET.SubElement(el, "note").text = c.note
        elements.append((c.record_in, c.record_in + c.duration, el))
        cursor = c.record_in + c.duration
    if inserts and not elements:
        g = ET.SubElement(spine, "gap", name="Gap", offset="0s", start="0s", duration=_rt(seq.duration, rate))
        elements.append((0.0, seq.duration, g))
    for c in inserts:
        # Connected clip on lane 1, attached to the spine element under its start.
        parent_start, _, parent = next(((s, e, el) for s, e, el in elements if s <= c.record_in < e), elements[-1])
        pel_start = parent.get("start", "0s")
        p_start = float(Fraction(pel_start[:-1])) if pel_start != "0s" else 0.0
        offset = p_start + (c.record_in - parent_start)
        ET.SubElement(parent, "asset-clip", ref=assets[c.media_path], lane="1", name=c.name, offset=_rt(offset, rate),
                      start=_rt(c.src_in, rate), duration=_rt(c.duration, rate), format="r0", tcFormat="NDF")
    ET.indent(root)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding="unicode")
    path.write_text(xml)


# ---------------------------------------------------------------- CMX 3600

def write_edl(seq: Sequence, path: Path, track: int = 1) -> None:
    rate = seq.rate
    drop = rate.denominator == 1001 and int(round(float(rate))) in (30, 60)
    lines = [f"TITLE: {seq.name[:70]}", f"FCM: {'DROP FRAME' if drop else 'NON-DROP FRAME'}", ""]
    n = 0
    for c in sorted((c for c in seq.clips if c.track == track), key=lambda c: c.record_in):
        n += 1
        reel = "".join(ch for ch in c.reel.upper() if ch.isalnum())[:8] or "AX"
        s_in = timecode(c.asset_offset + c.src_in, rate)
        s_out = timecode(c.asset_offset + c.src_out, rate)
        r_in = timecode(c.record_in, rate)
        r_out = timecode(c.record_in + c.duration, rate)
        chans = "B" if c.has_audio else "V"
        lines.append(f"{n:03d}  {reel:<8} {chans:<5} C        {s_in} {s_out} {r_in} {r_out}")
        lines.append(f"* FROM CLIP NAME: {c.name}")
        lines.append(f"* SOURCE FILE: {Path(c.media_path).name}")
        if c.note:
            lines.append(f"* COMMENT: {c.note[:200]}")
        lines.append("")
    path.write_text("\r\n".join(lines) + "\r\n")


_ = math
