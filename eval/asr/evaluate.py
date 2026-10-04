"""Speech recognition accuracy (WER) against human transcripts.

References are the subtitle files shipped with the openly licensed clips
(SRT/VTT). Each reference is clipped to the media duration, both sides are
normalised (lower case, digits kept, punctuation removed) and WER is word-level
Levenshtein distance / reference length.
usage: python evaluate.py <library_dir> <media_dir> [--json out.json]
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

PAIRS = {  # media filename -> reference file
    "shotstack_scott-ko.mp4": "shotstack_scott-ko.srt",
    "netflix_meridian_0000-0200_1080p60.mp4": "netflix_meridian_0000-0200_1080p60.en.srt",
    "tears_of_steel_0000-0200_512x292.mp4": "tears_of_steel_0000-0200_512x292.en.vtt",
    "cremad_10speakers_concat.mp4": "cremad_10speakers_concat.en.srt",
}
TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{3})\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d{3})")


def parse_subs(path: Path) -> list[tuple[float, float, str]]:
    cues, cur, buf = [], None, []
    for line in path.read_text(errors="replace").splitlines() + [""]:
        m = TS.search(line)
        if m:
            g = [int(x) for x in m.groups()]
            cur = (g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000)
            buf = []
        elif cur and line.strip():
            buf.append(re.sub(r"<[^>]+>", "", line.strip()))
        elif cur and not line.strip():
            cues.append((cur[0], cur[1], " ".join(buf)))
            cur = None
    return cues


def norm(t: str) -> list[str]:
    t = t.lower().replace("’", "'")
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|♪", " ", t)
    t = re.sub(r"[^\w' ]", " ", t)
    return [w.strip("'") for w in t.split() if w.strip("'")]


def wer(ref: list[str], hyp: list[str]) -> tuple[int, int]:
    d = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(hyp) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (ref[i - 1] != hyp[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(hyp)], len(ref)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("media")
    ap.add_argument("--json")
    a = ap.parse_args()
    db = sqlite3.connect(str(Path(a.library) / "library.sqlite"))
    out = {}
    E = N = 0
    for media, ref in PAIRS.items():
        row = db.execute("SELECT id, duration FROM assets WHERE filename=?", (media,)).fetchone()
        if not row:
            continue
        aid, dur = row
        status = db.execute("SELECT status, error FROM analysis_runs WHERE asset_id=? AND analyser='speech'", (aid,)).fetchone()
        hyp_text = " ".join(r[0] for r in db.execute("SELECT text FROM moments WHERE asset_id=? AND kind='speech' ORDER BY start_s", (aid,)))
        cues = [c for c in parse_subs(Path(a.media) / ref) if c[0] < (dur or 1e9)]
        ref_words = norm(" ".join(c[2] for c in cues))
        hyp_words = norm(hyp_text)
        e, n = wer(ref_words, hyp_words)
        E += e
        N += n
        lang = db.execute("SELECT value FROM signals WHERE asset_id=? AND name='audio.language'", (aid,)).fetchone()
        out[media] = {"wer": round(e / max(1, n), 3), "ref_words": n, "hyp_words": len(hyp_words), "speech_status": status[0] if status else None,
                      "language": json.loads(lang[0]) if lang else None, "hyp_excerpt": hyp_text[:160], "ref_excerpt": " ".join(ref_words[:25])}
    res = {"overall_wer": round(E / max(1, N), 3), "files": out}
    print(json.dumps(res, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    sys.exit(main())
