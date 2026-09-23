import wave

from silenttalk.smoke import create_test_tone


def test_fixed_smoke_tone_is_valid_wav(tmp_path) -> None:
    path = tmp_path / "tone.wav"
    create_test_tone(path, duration_seconds=0.1)
    with wave.open(str(path), "rb") as source:
        assert source.getframerate() == 48_000
        assert source.getnchannels() == 1
        assert source.getnframes() == 4_800
