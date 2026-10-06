import numpy as np
import pytest

from metachlorian.media import ffmpeg
from metachlorian.media.shots import Features, Params, detect


def cut_features(n, cut, fps=30):
    hist = np.zeros((n, 64), dtype=np.float32)
    hist[:cut, 0] = 3.0
    hist[cut:, 1] = 3.0
    small = np.full((n, 27, 48), 0.3, dtype=np.float32)
    small[cut:] = 0.7
    return Features(fps, hist, small, small.mean(axis=(1, 2)), np.full(n, 0.1))


@pytest.mark.parametrize('tail_frames', [1, 2, 9])
def test_final_cut_cannot_leave_a_shot_below_minimum(tail_frames):
    assert detect(cut_features(100, 100 - tail_frames), Params(min_shot_s=0.35)) == []


def test_final_cut_at_minimum_is_retained():
    boundaries = detect(cut_features(100, 90), Params(min_shot_s=0.35))
    assert [(b.frame, b.kind) for b in boundaries] == [(90, 'cut')]


def test_frame_after_eof_reports_decode_error(sample_video):
    with pytest.raises(RuntimeError, match='could not decode frame'):
        ffmpeg.frame_at(sample_video, 100.0)
