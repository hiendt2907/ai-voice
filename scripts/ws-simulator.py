#!/usr/bin/env python3
"""
WS Simulator — kết nối ws://localhost:8000/ws/call, gửi utterances,
thu audio_chunk về và lưu thành WAV để nghe.

Usage:
    python3 scripts/ws-simulator.py
"""

import asyncio
import base64
import json
import struct
import sys
import wave
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Cài websockets: pip install websockets")
    sys.exit(1)

WS_URL = "ws://localhost:8000/ws/call"
OUTPUT_WAV = Path("scripts/simulator-output.wav")

SCRIPT = {
    "type": "ai_driven",
    "execution_mode": "rag_assisted",
    "greeting": "Dạ, Doctor Check xin nghe ạ. Bạn cần hỗ trợ gì ạ?",
    "persona": {
        "fillers": ["Dạ vâng ạ", "Vâng ạ", "Dạ", "Dạ để em kiểm tra ạ"],
        "barge_in": True,
        "gender_detect": True,
    },
    "rag": {
        "enabled": True,
        "linkedKbTags": ["general", "booking", "pricing", "services", "hours", "insurance", "preparation", "doctors"],
    },
    "escalation": {
        "telegram": False,
        "chat_id": "",
        "bot_token": "",
        "template": "",
        "waiting_message": "Dạ em đã ghi nhận",
    },
    "fallback_message": "Dạ để em kiểm tra thêm thông tin ạ",
    "ragFallbackMessage": "Dạ em sẽ xem lại và phản hồi anh/chị sớm ạ",
}

UTTERANCES = [
    ("Phòng khám mở cửa mấy giờ?", 4.0),
    ("Gói khám tổng quát giá bao nhiêu?", 5.0),
    ("Tôi muốn đặt lịch khám", 5.0),
]

SAMPLE_RATE = 8000  # telephony 8kHz PCM


async def run():
    audio_frames: list[bytes] = []
    beats: list[dict] = []
    turn_texts: dict[int, str] = {}
    current_turn = [0]

    print(f"Kết nối {WS_URL} ...")

    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        # Gửi START
        start_msg = {
            "event": "start",
            "session_id": "sim-test-001",
            "campaign_id": "5185db02-7a2c-40de-8fa0-379a8e665858",
            "script_version_id": "1.0.0",
            "caller_number": "0900000000",
            "direction": "inbound",
            "use_real_tts": True,
            "script": SCRIPT,
        }
        await ws.send(json.dumps(start_msg))
        print("→ START gửi, đợi greeting...")

        utt_idx = 0
        hangup_received = False

        async def sender():
            nonlocal utt_idx
            for text, delay in UTTERANCES:
                if hangup_received:
                    break
                await asyncio.sleep(delay)
                print(f"\n→ UTTERANCE [{utt_idx + 1}]: {text!r}")
                await ws.send(json.dumps({"event": "utterance", "text": text}))
                utt_idx += 1
            # Đợi thêm rồi hangup
            await asyncio.sleep(6)
            print("\n→ HANGUP")
            await ws.send(json.dumps({"event": "hangup"}))

        sender_task = asyncio.create_task(sender())

        try:
            async for raw_msg in ws:
                msg = json.loads(raw_msg)
                event = msg.get("event", "")

                if event == "audio_chunk":
                    turn_num = msg.get("turn", 0)
                    current_turn[0] = turn_num
                    data = base64.b64decode(msg["data"])
                    audio_frames.append(data)
                    sys.stdout.write("▪")
                    sys.stdout.flush()

                elif event == "beat":
                    beat = msg
                    beats.append(beat)
                    turn_num = msg.get("turn", 0)
                    text = msg.get("text", "")
                    if text:
                        if turn_num not in turn_texts:
                            turn_texts[turn_num] = ""
                            print(f"\n← Turn {turn_num} Bot: ", end="")
                        print(text, end=" ")
                        sys.stdout.flush()
                        turn_texts[turn_num] = (turn_texts.get(turn_num, "") + " " + text).strip()

                elif event == "hangup":
                    print("\n← HANGUP nhận")
                    hangup_received = True
                    break

                elif event == "handoff":
                    print(f"\n← HANDOFF: {msg.get('reason', '')}")
                    break

        except Exception as e:
            print(f"\nWS error: {e}")
        finally:
            sender_task.cancel()

    print(f"\n\nTổng audio chunks: {len(audio_frames)}")
    print(f"Tổng turns: {len(turn_texts)}")
    for t, text in sorted(turn_texts.items()):
        print(f"  Turn {t}: {text[:100]}")

    # Ghép audio thành WAV
    if audio_frames:
        raw_audio = b"".join(audio_frames)

        # Detect encoding: PCM 16-bit (2 bytes/sample) or mulaw (1 byte/sample)
        # ws.py sends OutboundEvent.AUDIO_CHUNK with PCM 16-bit at 8kHz
        n_channels = 1
        sample_width = 2  # 16-bit PCM

        with wave.open(str(OUTPUT_WAV), "w") as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw_audio)

        duration_s = len(raw_audio) / (SAMPLE_RATE * sample_width * n_channels)
        print(f"\nLưu audio: {OUTPUT_WAV} ({duration_s:.1f}s, {len(raw_audio) // 1024}KB)")
        print(f"Phát: afplay {OUTPUT_WAV}")
    else:
        print("\nKhông có audio (beat-only mode). Bot đang chạy text-only.")
        print("Kiểm tra lại ELEVENLABS_API_KEY và USE_REAL_TTS=true trong .env")


if __name__ == "__main__":
    asyncio.run(run())
