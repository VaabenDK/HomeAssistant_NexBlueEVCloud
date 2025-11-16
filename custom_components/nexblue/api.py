from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import aiohttp
import json
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CHARGER_STATE_MAP, DEFAULT_ACCOUNT_TYPE, SCHEDULE_MODE_MAP


_LOGGER = logging.getLogger(__name__)


API_BASE_URL = "https://api.nexblue.com/third_party/openapi"
TOKEN_SAFETY_MARGIN = timedelta(seconds=30)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class NexblueAPIError(Exception):
    """Base class for Nexblue API errors."""


class NexblueAuthError(NexblueAPIError):
    """Raised when authentication fails."""


class NexblueCommandError(NexblueAPIError):
    """Raised when a command returns a failure result."""

    def __init__(self, result: int) -> None:
        super().__init__(f"Command failed with result code {result}")
        self.result = result


@dataclass
class NexblueChargerData:
    """Container for all data related to a charger."""

    relation: dict[str, Any]
    detail: dict[str, Any]
    status: dict[str, Any]
    schedule: dict[str, Any] | None = None

    @property
    def charger_id(self) -> str:
        return self.detail.get("serial_number") or self.relation.get("serial_number")

    @property
    def online(self) -> bool:
        return bool(self.detail.get("online", False))

    @property
    def charging_state(self) -> str | None:
        raw_state = self.status.get("charging_state")
        return CHARGER_STATE_MAP.get(raw_state)

    @property
    def current_limit(self) -> int | None:
        value = self.status.get("current_limit")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def schedule_mode_id(self) -> int | None:
        schedule = self.schedule or {}
        value = schedule.get("schedule_mode")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def schedule_mode(self) -> str | None:
        mode_id = self.schedule_mode_id
        if mode_id is None:
            return None
        return SCHEDULE_MODE_MAP.get(mode_id)

    @property
    def uk_reg(self) -> bool:
        schedule = self.schedule or {}
        return bool(schedule.get("uk_reg"))

    @property
    def circuit_fuse(self) -> int | None:
        circuit = self.detail.get("circuit_data")
        if isinstance(circuit, dict):
            try:
                fuse = circuit.get("fuse")
                return int(fuse) if fuse is not None else None
            except (TypeError, ValueError):
                return None
        return None

    @property
    def max_configurable_current(self) -> int:
        fuse = self.circuit_fuse
        max_limit = 32 if fuse is None else min(32, fuse)
        return max(6, max_limit)


class NexblueAPI:
    """Small async client for the Nexblue open API."""

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        account_type: int = DEFAULT_ACCOUNT_TYPE,
    ) -> None:
        self._hass = hass
        self._email = email
        self._password = password
        self._account_type = account_type
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: datetime | None = None

    async def get_chargers(self) -> dict[str, NexblueChargerData]:
        """Return the current state for all chargers."""

        relations = await self._request("GET", "/chargers")
        relation_items: list[dict[str, Any]] = relations.get("data", []) if relations else []

        if not relation_items:
            return {}

        async def _fetch_single(relation: dict[str, Any]) -> tuple[str, NexblueChargerData | None]:
            charger_id = relation.get("serial_number")
            if not charger_id:
                _LOGGER.debug("Skipping relation without serial number: %s", relation)
                return "", None

            detail_result, status_result, schedule_result = await asyncio.gather(
                self._request("GET", f"/chargers/{charger_id}"),
                self._request("GET", f"/chargers/{charger_id}/cmd/status"),
                self._request("GET", f"/chargers/{charger_id}/cmd/schedule"),
                return_exceptions=True,
            )

            detail: dict[str, Any] = {}
            status: dict[str, Any] = {}
            schedule: dict[str, Any] | None = None

            if isinstance(detail_result, Exception):
                _LOGGER.warning("Failed to fetch charger %s detail: %s", charger_id, detail_result)
            else:
                detail = detail_result or {}

            if isinstance(status_result, Exception):
                _LOGGER.warning("Failed to fetch charger %s status: %s", charger_id, status_result)
            else:
                status = status_result or {}

            if isinstance(schedule_result, Exception):
                _LOGGER.debug("Failed to fetch charger %s schedule: %s", charger_id, schedule_result)
            else:
                schedule = schedule_result or {}

            return charger_id, NexblueChargerData(
                relation=relation,
                detail=detail,
                status=status,
                schedule=schedule,
            )

        results = await asyncio.gather(*[_fetch_single(relation) for relation in relation_items])

        chargers: dict[str, NexblueChargerData] = {}
        for charger_id, data in results:
            if charger_id and data:
                chargers[charger_id] = data

        return chargers

    async def start_charging(self, charger_id: str) -> None:
        """Send start charging command."""

        response = await self._request("POST", f"/chargers/{charger_id}/cmd/start_charging")
        result = response.get("result") if isinstance(response, dict) else None
        if result not in (None, 0):
            raise NexblueCommandError(result)

    async def stop_charging(self, charger_id: str) -> None:
        """Send stop charging command."""

        response = await self._request("POST", f"/chargers/{charger_id}/cmd/stop_charging")
        result = response.get("result") if isinstance(response, dict) else None
        if result not in (None, 0):
            raise NexblueCommandError(result)

    async def set_current_limit(self, charger_id: str, current_limit: int) -> None:
        """Set the charger current limit."""

        payload = {"current_limit": int(current_limit)}
        response = await self._request(
            "POST",
            f"/chargers/{charger_id}/cmd/set_current_limit",
            json_data=payload,
        )
        result = response.get("result") if isinstance(response, dict) else None
        if result not in (None, 0):
            raise NexblueCommandError(result)

    async def set_schedule_mode(self, charger_id: str, schedule_mode: int) -> None:
        """Switch the charger schedule mode."""

        payload = {"schedule_mode": int(schedule_mode)}
        response = await self._request(
            "PUT",
            f"/chargers/{charger_id}/cmd/schedule/config",
            json_data=payload,
        )
        result = response.get("result") if isinstance(response, dict) else None
        if result not in (None, 0):
            raise NexblueCommandError(result)

    async def _ensure_access_token(self) -> None:
        if self._access_token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return

        if self._refresh_token:
            try:
                await self._refresh_access_token()
                return
            except NexblueAPIError as exc:
                _LOGGER.debug("Token refresh failed: %s. Falling back to full login", exc)

        await self._login()

    async def _login(self) -> None:
        payload = {
            "username": self._email,
            "password": self._password,
            "account_type": self._account_type,
        }
        try:
            data = await self._request("POST", "/account/login", json_data=payload, auth_required=False)
        except NexblueAPIError as exc:
            raise NexblueAuthError("Authentication with Nexblue failed") from exc
        if not isinstance(data, dict):
            raise NexblueAuthError("Invalid response when logging in")
        self._update_tokens(data)
        _LOGGER.debug("Logged in to Nexblue as %s", self._email)

    async def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise NexblueAuthError("Missing refresh token")

        payload = {
            "refresh_token": self._refresh_token,
            "account_type": self._account_type,
        }
        try:
            data = await self._request("POST", "/account/refresh_token", json_data=payload, auth_required=False)
        except NexblueAPIError as exc:
            raise NexblueAuthError("Refreshing Nexblue token failed") from exc
        if not isinstance(data, dict):
            raise NexblueAuthError("Invalid response when refreshing token")
        self._update_tokens(data, keep_refresh=True)
        _LOGGER.debug("Refreshed Nexblue access token")

    def _update_tokens(self, data: dict[str, Any], *, keep_refresh: bool = False) -> None:
        self._access_token = data.get("access_token")
        expires_in = max(int(data.get("expires_in", 3600)), 0)
        expires_delta = timedelta(seconds=expires_in)
        now = datetime.now(timezone.utc)
        if expires_delta <= TOKEN_SAFETY_MARGIN:
            self._token_expiry = now + timedelta(seconds=5)
        else:
            self._token_expiry = now + (expires_delta - TOKEN_SAFETY_MARGIN)
        if not keep_refresh:
            self._refresh_token = data.get("refresh_token")
        elif data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]

        if not self._access_token:
            raise NexblueAuthError("Missing access token in response")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        auth_required: bool = True,
        retry: bool = True,
    ) -> Any:
        if auth_required:
            await self._ensure_access_token()

        session = async_get_clientsession(self._hass)
        headers: dict[str, str] = {}
        if auth_required and self._access_token:
            headers["Authorization"] = self._access_token

        url = f"{API_BASE_URL}{path}"

        try:
            async with session.request(
                method,
                url,
                json=json_data,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                text = await response.text()
                data: Any
                if text:
                    try:
                        data = json.loads(text)
                    except ValueError:
                        data = text
                else:
                    data = None

                if response.status == 401 and auth_required:
                    if retry:
                        _LOGGER.debug("Received 401 from Nexblue, attempting to refresh token")
                        await self._handle_unauthorized()
                        return await self._request(
                            method,
                            path,
                            params=params,
                            json_data=json_data,
                            auth_required=auth_required,
                            retry=False,
                        )
                    raise NexblueAuthError("Unauthorized")

                if response.status >= 400:
                    message = self._extract_error_message(data)
                    raise NexblueAPIError(f"HTTP {response.status}: {message}")

                return data

        except aiohttp.ClientError as exc:
            raise NexblueAPIError(f"Error communicating with Nexblue API: {exc}") from exc

    async def _handle_unauthorized(self) -> None:
        self._access_token = None
        self._token_expiry = None
        if self._refresh_token:
            await self._refresh_access_token()
        else:
            await self._login()

    @staticmethod
    def _extract_error_message(data: Any) -> str:
        if isinstance(data, dict):
            for key in ("msg", "message", "error"):
                if key in data:
                    return str(data[key])
        if isinstance(data, str):
            return data
        return "Unknown error"