"""Factory for per-connection telephony adapters.

Adding a new provider: implement TelephonyAdapter in its own module, add one
branch here. Nothing in api/routers/ws.py needs to change.
"""

from __future__ import annotations

from api.config import Settings
from telephony.base import TelephonyAdapter
from telephony.cloudfone import CloudFoneAdapter
from telephony.freeswitch import FreeSwitchAdapter


def get_adapter(provider: str, *, settings: Settings, audio_mode: str = "json") -> TelephonyAdapter:
    if provider == "cloudfone":
        return CloudFoneAdapter()
    if provider == "freeswitch":
        return FreeSwitchAdapter(binary_stream=audio_mode == "stream")
    raise ValueError(f"Unknown telephony provider: {provider!r}")
