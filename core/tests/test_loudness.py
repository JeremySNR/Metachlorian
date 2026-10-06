from metachlorian.media import ffmpeg
import numpy as np
import wave


def test_r128_contains_momentary_measurements(tmp_path):
    sample_audio = tmp_path / 'tone.wav'
    sr = 16000
    samples = (0.1 * np.sin(2 * np.pi * 440 * np.arange(sr * 6) / sr) * 32767).astype('<i2')
    with wave.open(str(sample_audio), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(samples.tobytes())
    loud = ffmpeg.loudness(sample_audio)
    assert loud['integrated_lufs'] is not None
    assert loud['true_peak_dbfs'] is not None
    curve = loud['momentary']
    assert len(curve) >= 50  # six-second fixture, one measurement per 100 ms
    times = [t for t, _ in curve]
    assert times == sorted(times)
    assert times[-1] > 5.5
    assert any(-60 < value < 0 for _, value in curve)
