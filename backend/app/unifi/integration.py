from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import Settings
from app.timeutil import parse_iso_datetime
from app.unifi.errors import (
    UniFiAPIError,
    UniFiAuthError,
    UniFiRateLimited,
    UniFiUnavailable,
)
from app.unifi.types import LiveClient, normalize_host, normalize_mac

USER_AGENT = "UniFiWifiTool/0.1"


class IntegrationClient:
    """Official Network Integration API (X-API-KEY)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = normalize_host(settings.unifi_host)
        self._http = httpx.Client(
            timeout=settings.unifi_timeout_seconds,
            verify=settings.tls_verify,
            headers={
                "X-API-KEY": settings.unifi_api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        self._site: tuple[str, str] | None = None

    def close(self) -> None:
        self._http.close()

    # -- plumbing ---------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any | None = None,
        retries: int = 2,
    ) -> Any:
        url = f"{self.base_url}/proxy/network/integration/v1{path}"
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._http.request(method, url, params=params, json=json)
            except httpx.RequestError as exc:
                raise UniFiUnavailable(f"Could not reach the controller: {exc}") from exc

            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                if attempt < retries:
                    time.sleep(min(retry_after, 5.0))
                    last_error = UniFiRateLimited("Controller rate limit reached")
                    continue
                raise UniFiRateLimited("Controller rate limit reached")

            if response.status_code >= 500 and attempt < retries:
                time.sleep(0.5 * (2**attempt))
                last_error = UniFiAPIError(
                    f"Controller returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
                continue

            if response.status_code in {401, 403}:
                raise UniFiAuthError(
                    "API key rejected. Check UNIFI_API_KEY and that the key has access to this site."
                )
            if response.status_code >= 400:
                raise UniFiAPIError(
                    _error_message(response),
                    status_code=response.status_code,
                    payload=_safe_json(response),
                )
            return _safe_json(response)

        raise last_error or UniFiUnavailable("Controller request failed")

    # -- reads ------------------------------------------------------------
    def info(self) -> dict:
        return self._request("GET", "/info")

    def list_sites(self) -> list[dict]:
        return list(self._paginate("/sites"))

    def resolve_site(self) -> tuple[str, str]:
        if self._site is not None:
            return self._site

        sites = self.list_sites()
        configured_id = self.settings.unifi_site_id.strip()
        configured_name = self.settings.unifi_site.strip()

        chosen: dict | None = None
        if configured_id:
            chosen = next((site for site in sites if site.get("id") == configured_id), None)
        if chosen is None and configured_name:
            needle = configured_name.casefold()
            chosen = next(
                (
                    site
                    for site in sites
                    if str(site.get("internalReference", "")).casefold() == needle
                    or str(site.get("name", "")).casefold() == needle
                ),
                None,
            )
        if chosen is None and sites:
            chosen = sites[0]
        if chosen is None:
            raise UniFiAPIError(
                "No sites returned by the controller. Create a site or set UNIFI_SITE_ID."
            )

        self._site = (str(chosen["id"]), str(chosen.get("name") or chosen.get("internalReference") or ""))
        return self._site

    def list_clients(self, site_id: str | None = None) -> list[LiveClient]:
        site_id = site_id or self.resolve_site()[0]
        clients: list[LiveClient] = []
        for item in self._paginate(f"/sites/{site_id}/clients"):
            raw_mac = item.get("macAddress")
            if not raw_mac:
                continue
            try:
                mac = normalize_mac(str(raw_mac))
            except ValueError:
                continue
            last_seen = parse_iso_datetime(item.get("connectedAt"))
            clients.append(
                LiveClient(
                    mac=mac,
                    name=item.get("name") or None,
                    hostname=item.get("name") or None,
                    ip_address=item.get("ipAddress") or None,
                    blocked=None,
                    connected=True,
                    last_seen_at=last_seen,
                    source="integration",
                    unifi_client_id=item.get("id"),
                    connection_type=str(item.get("type") or "").lower() or None,
                )
            )
        return clients

    def list_wifi_broadcasts(self, site_id: str | None = None) -> list[dict]:
        site_id = site_id or self.resolve_site()[0]
        return list(self._paginate(f"/sites/{site_id}/wifi/broadcasts"))

    def get_wifi_broadcast(self, broadcast_id: str, site_id: str | None = None) -> dict:
        site_id = site_id or self.resolve_site()[0]
        return self._request("GET", f"/sites/{site_id}/wifi/broadcasts/{broadcast_id}")

    def update_wifi_broadcast(
        self, broadcast_id: str, payload: dict, site_id: str | None = None
    ) -> dict:
        site_id = site_id or self.resolve_site()[0]
        return self._request(
            "PUT", f"/sites/{site_id}/wifi/broadcasts/{broadcast_id}", json=payload
        )

    # -- helpers ----------------------------------------------------------
    def _paginate(self, path: str):
        offset = 0
        limit = 200
        for _ in range(100):
            page = self._request(
                "GET", path, params={"offset": offset, "limit": limit}
            )
            items = page.get("data") or []
            yield from items
            total = page.get("totalCount")
            offset += len(items)
            if not items:
                return
            if isinstance(total, int) and offset >= total:
                return


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _error_message(response: httpx.Response) -> str:
    payload = _safe_json(response)
    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            if payload.get(key):
                return str(payload[key])
    text = response.text.strip()
    return text[:300] if text else f"Controller returned HTTP {response.status_code}"


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value else 1.0
    except ValueError:
        return 1.0
