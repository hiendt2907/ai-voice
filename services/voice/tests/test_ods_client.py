from cloudfone.ods_client import OdsClient, OdsConfig


def test_ods_client_not_configured():
    cfg = OdsConfig(ods_url="", api_key="", tenant_id="")
    client = OdsClient(cfg)
    assert client.is_configured is False


def test_ods_client_configured():
    cfg = OdsConfig(ods_url="wss://ods.cloudfone.vn/ws", api_key="key", tenant_id="dc")
    client = OdsClient(cfg)
    assert client.is_configured is True


def test_ods_client_status_pending():
    cfg = OdsConfig(ods_url="", api_key="", tenant_id="")
    client = OdsClient(cfg)
    status = client.get_status()
    assert status["status"] == "pending_schema"
    assert "mock" in status["note"]
