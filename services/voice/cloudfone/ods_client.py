"""CloudFone ODS WebSocket client (production integration stub).

Connects to the real CloudFone ODS gateway when ODS documentation is available.
Currently blocked — ODS WS schema pending from CloudFone team.

Sprint 6 placeholder: implements the interface that ws.py will call when
CLOUDFONE_ODS_URL is configured in the environment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OdsConfig:
    ods_url: str
    api_key: str
    tenant_id: str


class OdsClient:
    """Production ODS client — implementation pending ODS schema delivery."""

    def __init__(self, config: OdsConfig) -> None:
        self._config = config

    @property
    def is_configured(self) -> bool:
        return bool(self._config.ods_url and self._config.api_key)

    def get_status(self) -> dict[str, str]:
        return {
            "status": "pending_schema",
            "ods_url": self._config.ods_url or "not_set",
            "note": "ODS WS schema pending from CloudFone team — using mock gateway",
        }
