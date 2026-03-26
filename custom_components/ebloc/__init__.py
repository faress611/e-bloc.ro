"""Inițializarea integrării E-bloc România."""

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LICENSE_DATA_KEY,
    PLATFORMS,
)
from .api import EblocApiClient
from .coordinator import EblocCoordinator
from .license import LicenseManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class EblocRuntimeData:
    """Structură tipizată pentru datele runtime ale integrării."""

    coordinator: EblocCoordinator | None = None
    api_client: EblocApiClient | None = None


async def async_setup(hass: HomeAssistant, config: dict):
    """Configurează integrarea globală E-bloc România."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configurează integrarea pentru o anumită intrare (config entry)."""
    _LOGGER.info(
        "[Ebloc] Se configurează integrarea (entry_id=%s).",
        entry.entry_id,
    )

    hass.data.setdefault(DOMAIN, {})

    # ── Inițializare License Manager (o singură instanță per domeniu) ──
    if LICENSE_DATA_KEY not in hass.data.get(DOMAIN, {}):
        _LOGGER.debug("[Ebloc] Inițializez LicenseManager (prima entry)")
        license_mgr = LicenseManager(hass)
        await license_mgr.async_load()
        hass.data[DOMAIN][LICENSE_DATA_KEY] = license_mgr
        _LOGGER.debug(
            "[Ebloc] LicenseManager: status=%s, valid=%s, fingerprint=%s...",
            license_mgr.status,
            license_mgr.is_valid,
            license_mgr.fingerprint[:16],
        )

        # Heartbeat periodic
        from datetime import timedelta
        from homeassistant.helpers.event import async_track_time_interval

        interval_sec = license_mgr.check_interval_seconds
        _LOGGER.debug(
            "[Ebloc] Programez heartbeat periodic la fiecare %d secunde",
            interval_sec,
        )

        async def _heartbeat_periodic(_now) -> None:
            """Verifică statusul la server dacă cache-ul a expirat."""
            mgr: LicenseManager | None = hass.data.get(DOMAIN, {}).get(
                LICENSE_DATA_KEY
            )
            if not mgr:
                return
            if mgr.needs_heartbeat:
                _LOGGER.debug("[Ebloc] Heartbeat: cache expirat, verific la server")
                await mgr.async_heartbeat()

        cancel_heartbeat = async_track_time_interval(
            hass,
            _heartbeat_periodic,
            timedelta(seconds=interval_sec),
        )
        hass.data[DOMAIN]["_cancel_heartbeat"] = cancel_heartbeat

        # Notificare re-enable
        was_disabled = hass.data.pop(f"{DOMAIN}_was_disabled", False)
        if was_disabled:
            await license_mgr.async_notify_event("integration_enabled")

        if not license_mgr.is_valid:
            _LOGGER.warning(
                "[Ebloc] Integrarea nu are licență validă. "
                "Senzorii vor afișa 'Licență necesară'."
            )
        elif license_mgr.is_trial_valid:
            _LOGGER.info(
                "[Ebloc] Perioadă de evaluare — %d zile rămase",
                license_mgr.trial_days_remaining,
            )
        else:
            _LOGGER.info(
                "[Ebloc] Licență activă — tip: %s",
                license_mgr.license_type,
            )
    else:
        _LOGGER.debug("[Ebloc] LicenseManager există deja (entry suplimentară)")

    # ── Client API ──
    session = async_get_clientsession(hass)
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api_client = EblocApiClient(session, email, password)

    # Injectăm sesiunea salvată (dacă există)
    saved_session = entry.data.get("session_data")
    if saved_session:
        api_client.inject_session(saved_session)
        _LOGGER.debug("[Ebloc] Sesiune injectată din config_entry")

    # ── Coordinator (cu interval configurabil) ──
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = EblocCoordinator(hass, api_client, entry, update_interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error(
            "[Ebloc] Prima actualizare eșuată (entry_id=%s): %s",
            entry.entry_id,
            err,
        )
        return False

    # Salvăm datele runtime
    entry.runtime_data = EblocRuntimeData(
        coordinator=coordinator,
        api_client=api_client,
    )

    # Încărcăm platformele (NECONDIȚIONAT — gating-ul e în sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listener pentru modificarea opțiunilor
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info(
        "[Ebloc] Integrarea configurată (entry_id=%s).",
        entry.entry_id,
    )
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reîncarcă integrarea când opțiunile se schimbă."""
    _LOGGER.info("[Ebloc] Opțiunile s-au schimbat. Se reîncarcă...")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Descărcarea intrării din config_entries."""
    _LOGGER.info(
        "[Ebloc] async_unload_entry entry_id=%s",
        entry.entry_id,
    )

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        remaining_entries = hass.config_entries.async_entries(DOMAIN)
        entry_ids_ramase = {
            e.entry_id for e in remaining_entries if e.entry_id != entry.entry_id
        }

        if not entry_ids_ramase:
            _LOGGER.info("[Ebloc] Ultima entry descărcată — curăț domeniul complet")

            # Notificare lifecycle
            mgr = hass.data[DOMAIN].get(LICENSE_DATA_KEY)
            if mgr and not hass.is_stopping:
                if entry.disabled_by:
                    await mgr.async_notify_event("integration_disabled")
                    hass.data[f"{DOMAIN}_was_disabled"] = True
                else:
                    hass.data.setdefault(f"{DOMAIN}_notify", {}).update(
                        {
                            "fingerprint": mgr.fingerprint,
                            "license_key": mgr._data.get("license_key", ""),
                        }
                    )

            # Oprește heartbeat
            cancel_hb = hass.data[DOMAIN].pop("_cancel_heartbeat", None)
            if cancel_hb:
                cancel_hb()
                _LOGGER.debug("[Ebloc] Heartbeat oprit")

            # Elimină LicenseManager
            hass.data[DOMAIN].pop(LICENSE_DATA_KEY, None)

            # Elimină domeniul complet
            hass.data.pop(DOMAIN, None)

            _LOGGER.info("[Ebloc] Cleanup complet")
    else:
        _LOGGER.error("[Ebloc] Unload EȘUAT pentru entry_id=%s", entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Notifică serverul când integrarea e complet eliminată."""
    _LOGGER.debug("[Ebloc] async_remove_entry entry_id=%s", entry.entry_id)

    remaining = hass.config_entries.async_entries(DOMAIN)
    if not remaining:
        notify_data = hass.data.pop(f"{DOMAIN}_notify", None)
        if notify_data and notify_data.get("fingerprint"):
            await _send_lifecycle_event(
                hass,
                notify_data["fingerprint"],
                notify_data.get("license_key", ""),
                "integration_removed",
            )


async def _send_lifecycle_event(
    hass: HomeAssistant, fingerprint: str, license_key: str, action: str
) -> None:
    """Trimite un eveniment lifecycle direct (fără LicenseManager)."""
    import hashlib
    import hmac as hmac_lib
    import json
    import time

    import aiohttp

    from .license import INTEGRATION, LICENSE_API_URL

    timestamp = int(time.time())
    payload = {
        "fingerprint": fingerprint,
        "timestamp": timestamp,
        "action": action,
        "license_key": license_key,
        "integration": INTEGRATION,
    }
    data = {k: v for k, v in payload.items() if k != "hmac"}
    msg = json.dumps(data, sort_keys=True).encode()
    payload["hmac"] = hmac_lib.new(
        fingerprint.encode(), msg, hashlib.sha256
    ).hexdigest()

    try:
        session = async_get_clientsession(hass)
        async with session.post(
            f"{LICENSE_API_URL}/notify",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Ebloc-HA-Integration/3.0",
            },
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                if not result.get("success"):
                    _LOGGER.warning(
                        "[Ebloc] Server a refuzat '%s': %s",
                        action,
                        result.get("error"),
                    )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("[Ebloc] Nu s-a putut raporta '%s': %s", action, err)
