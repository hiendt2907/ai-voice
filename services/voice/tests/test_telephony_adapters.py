import pytest

from telephony.cloudfone import CloudFoneAdapter
from telephony.registry import get_adapter
from api.config import Settings


def test_cloudfone_adapter_is_identity_passthrough():
    adapter = CloudFoneAdapter()
    raw = {"event": "start", "session_id": "s1"}
    assert adapter.normalize_inbound(raw) == raw
    assert adapter.encode_outbound(raw) == [raw]


@pytest.mark.asyncio
async def test_cloudfone_adapter_on_call_end_is_noop():
    adapter = CloudFoneAdapter()
    await adapter.on_call_end("hangup", "session-1")  # must not raise


def test_registry_returns_adapter_by_name():
    settings = Settings()
    assert isinstance(get_adapter("cloudfone", settings=settings), CloudFoneAdapter)
    with pytest.raises(ValueError):
        get_adapter("unknown", settings=settings)
