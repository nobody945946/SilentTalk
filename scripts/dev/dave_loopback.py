"""Discord voice receive end to end, offline: real DAVE, real transport crypto.

Plays the part of Discord's voice server (the MLS external sender) to put two
davey sessions into one real end-to-end-encrypted group, then sends speech the
way a Discord client does - Opus in 20 ms frames, DAVE-encrypted by the
speaker, RTP with a header extension (some packets padded), transport
encryption aead_xchacha20_poly1305_rtpsize, trailing silence frames - into
voice_recv's own AudioReader.callback holding the listener's session. What
comes out is decoded and the local STT is scored on it (character error rate)
against the same audio fed to STT directly.

    python scripts/dev/dave_loopback.py            # the app's receive path
    python scripts/dev/dave_loopback.py --no-dave  # frames not DAVE-decrypted
                                                   # (the old fork's failure)

Needs `cryptography` (dev only) to sign the proposals as the server would.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import davey
import discord.opus
import nacl.bindings
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from discord.ext.voice_recv.reader import AudioReader, PacketDecryptor

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from silenttalk import voice_recv_patch  # noqa: E402
from silenttalk.config import CopilotConfig  # noqa: E402
from silenttalk.copilot.smoke import (  # noqa: E402
    DISCORD_FRAME_BYTES,
    build_transcriber,
    char_error_rate,
    transcribe_pcm,
)
from silenttalk.copilot.stt_offline import audio_stats, pcm_to_mono  # noqa: E402

CHANNEL_ID = 927310423890473011
SPEAKER_ID, LISTENER_ID = 1001, 2002
SSRC = 0x1234
MODE = "aead_xchacha20_poly1305_rtpsize"
SILENCE = b"\xf8\xff\xfe"
SAMPLES_DIR = PROJECT_DIR / ".runtime" / "dev" / "stt_samples"
SAMPLES = (
    ("u01", "左邊有人，快點過來幫我"),
    ("u05", "等一下我去倒個水馬上回來"),
    ("u07", "剛剛那波團戰真的打得很好"),
    ("u08", "你們有人看過昨天的直播嗎"),
    ("u12", "晚餐要吃什麼，要不要叫外送"),
    ("u16", "誰有空幫我解一下這個任務"),
)


def _varint(n: int) -> bytes:
    if n < 1 << 6:
        return bytes([n])
    if n < 1 << 14:
        return (0x4000 | n).to_bytes(2, "big")
    return (0x80000000 | n).to_bytes(4, "big")


def _opaque(data: bytes) -> bytes:
    return _varint(len(data)) + data


def make_group() -> tuple[davey.DaveSession, davey.DaveSession]:
    """Speaker and listener in one MLS group, as the voice server builds it:
    it signs an Add proposal for the listener's key package (RFC 9420
    PublicMessage from an external sender), the speaker commits it, the
    listener joins from the Welcome."""
    server = davey.generate_p256_keypair()
    signer = ec.derive_private_key(
        int.from_bytes(server.private, "big"), ec.SECP256R1()
    )
    external_sender = _opaque(server.public) + struct.pack(">H", 1) + _opaque(b"\x00")
    speaker = davey.DaveSession(1, SPEAKER_ID, CHANNEL_ID)
    listener = davey.DaveSession(1, LISTENER_ID, CHANNEL_ID)
    for session in (speaker, listener):
        session.set_external_sender(external_sender)
    speaker.get_serialized_key_package()
    content = (
        _opaque(CHANNEL_ID.to_bytes(8, "big"))
        + (0).to_bytes(8, "big")  # epoch
        + b"\x02"  # sender: external
        + (0).to_bytes(4, "big")  # external sender index
        + _opaque(b"")  # authenticated data
        + b"\x02"  # content: proposal
        + struct.pack(">H", 1)  # add
        + listener.get_serialized_key_package()
    )
    tbs = struct.pack(">HH", 1, 1) + content  # mls10, public message
    signature = signer.sign(
        _opaque(b"MLS 1.0 FramedContentTBS") + _opaque(tbs), ec.ECDSA(hashes.SHA256())
    )
    message = struct.pack(">HH", 1, 1) + content + _opaque(signature)
    result = speaker.process_proposals(
        davey.ProposalsOperationType.append, _varint(len(message)) + message
    )
    if result is None or not result.welcome:
        raise RuntimeError("the speaker did not commit the Add proposal")
    speaker.process_commit(result.commit)
    listener.process_welcome(result.welcome)
    if not (speaker.ready and listener.ready):
        raise RuntimeError("the DAVE group did not become ready")
    return speaker, listener


def opus_frames(pcm: bytes) -> list[bytes]:
    encoder = discord.opus.Encoder()
    frames = []
    for start in range(0, len(pcm), DISCORD_FRAME_BYTES):
        chunk = pcm[start : start + DISCORD_FRAME_BYTES].ljust(
            DISCORD_FRAME_BYTES, b"\0"
        )
        frames.append(encoder.encode(chunk, encoder.SAMPLES_PER_FRAME))
    return frames + [SILENCE] * 5


def rtp_packets(
    frames: list[bytes], speaker: davey.DaveSession, key: bytes, pad_every: int = 7
) -> list[bytes]:
    """What a Discord client sends: DAVE on the Opus frame (silence stays
    plain), then RTP with a one-byte header extension, some packets padded
    (RFC 3550), and the rtpsize AEAD transport layer with a 4-byte nonce."""
    packets = []
    for n, frame in enumerate(frames):
        payload = frame if frame == SILENCE else speaker.encrypt_opus(frame)
        padded = bool(pad_every) and n % pad_every == 0
        first = 0x80 | 0x10 | (0x20 if padded else 0)  # V=2, X=1, P
        header = struct.pack(
            ">BBHII", first, 0x78, n & 0xFFFF, (n * 960) & 0xFFFFFFFF, SSRC
        )
        extension_header = b"\xbe\xde\x00\x01"
        body = b"\x10\x7f\x00\x00" + payload + (b"\0\0\0\x04" if padded else b"")
        nonce = n.to_bytes(4, "big")
        sealed = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            body, header + extension_header, nonce + bytes(20), key
        )
        packets.append(header + extension_header + sealed + nonce)
    return packets


def receive(
    packets: list[bytes],
    key: bytes,
    session: object | None,
    *,
    speaker_known: bool = True,
) -> list[bytes]:
    """voice_recv's AudioReader.callback on each packet, as the socket
    listener calls it; returns the Opus payloads it hands the jitter buffer.
    `speaker_known=False`: the voice gateway hasn't mapped the SSRC yet."""
    out: list[bytes] = []
    mapping = {SSRC: SPEAKER_ID} if speaker_known else {}
    voice_client = SimpleNamespace(
        mode=MODE,
        secret_key=key,
        _connection=SimpleNamespace(dave_session=session, dave_protocol_version=1),
        _ssrc_to_id=mapping,
        _get_id_from_ssrc=mapping.get,
    )
    reader = AudioReader.__new__(AudioReader)
    reader.voice_client = voice_client
    reader.error = None
    reader.decryptor = PacketDecryptor(MODE, key)
    reader.speaking_timer = SimpleNamespace(notify=lambda ssrc: None)
    reader.packet_router = SimpleNamespace(
        feed_rtp=lambda packet: out.append(bytes(packet.decrypted_data)),
        feed_rtcp=lambda packet: None,
    )
    for packet in packets:
        reader.callback(packet)
    return out


def decode(frames: list[bytes]) -> bytes:
    decoder = discord.opus.Decoder()
    pcm = bytearray()
    for frame in frames:
        try:
            pcm += decoder.decode(frame, fec=False)
        except discord.opus.OpusError:
            pcm += decoder.decode(None, fec=False)
    return bytes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--no-dave", action="store_true", help="listener without a DAVE session"
    )
    args = parser.parse_args()
    voice_recv_patch.apply()
    discord.opus._load_default()
    transcriber, collector = build_transcriber(
        PROJECT_DIR, CopilotConfig(stt_engine="sensevoice")
    )
    transcriber.start()
    direct_rates, received_rates = [], []
    try:
        for name, reference in SAMPLES:
            pcm = (SAMPLES_DIR / f"{name}.pcm").read_bytes()
            speaker, listener = make_group()
            key = bytes(range(32))
            frames = opus_frames(pcm)
            packets = rtp_packets(frames, speaker, key)
            got = receive(packets, key, None if args.no_dave else listener)
            sent_speech = [f for f in frames if f != SILENCE]
            exact = got[: len(sent_speech)] == sent_speech
            heard_pcm = decode(got)
            direct = transcribe_pcm(transcriber, collector, decode(frames))
            heard = transcribe_pcm(transcriber, collector, heard_pcm)
            direct_rates.append(char_error_rate(reference, direct))
            received_rates.append(char_error_rate(reference, heard))
            level, flatness = audio_stats(pcm_to_mono(heard_pcm)[::3])
            stats = listener.get_decryption_stats(SPEAKER_ID)
            print(
                f"{name}: {len(packets)} packets -> {len(got)} frames, "
                f"identical Opus {exact}, CER direct {direct_rates[-1]:.0%} / "
                f"received {received_rates[-1]:.0%}, heard {len(heard)} chars, "
                f"level {level:.1f} dBFS, flatness {flatness:.2f}, DAVE "
                f"{stats.attempts}/{stats.successes}/{stats.failures}/{stats.passthroughs}"
            )
    finally:
        transcriber.stop()
    print(
        f"average CER: direct {statistics.fmean(direct_rates):.1%}, "
        f"through the receive path {statistics.fmean(received_rates):.1%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
