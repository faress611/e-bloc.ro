"""Funcții helper comune pentru integrarea E-bloc România.

Centralizează utilitarele folosite de sensor.py, button.py, number.py, diagnostics.py:
  - is_license_valid: verificare licență
  - luna_ro: conversie dată '2026-02-26' → '26 februarie 2026'
  - luna_ro_scurt: conversie lună '2026-02' → 'februarie'
  - mascheaza_email: maschează email-ul pentru diagnostic
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    LICENSE_DATA_KEY,
    LUNI_RO,
)


def is_license_valid(hass: HomeAssistant) -> bool:
    """Verifică dacă licența este validă (folosit în async_setup_entry)."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if mgr is None:
        return False
    return mgr.is_valid


def luna_ro(luna_str: str) -> str:
    """Convertește dată sau lună în format românesc.

    '2026-02-26' → '26 februarie 2026'
    '2026-02'    → 'februarie 2026'
    """
    if not luna_str:
        return ""
    parts = luna_str.split("-")
    if len(parts) == 3:
        an, luna, zi = parts
        luna_name = LUNI_RO.get(luna, luna)
        return f"{int(zi)} {luna_name} {an}"
    if len(parts) == 2:
        an, luna = parts
        luna_name = LUNI_RO.get(luna, luna)
        return f"{luna_name} {an}"
    return luna_str


def luna_ro_scurt(luna_str: str) -> str:
    """Convertește '2026-02' → 'februarie' (doar numele lunii)."""
    if not luna_str:
        return ""
    parts = luna_str.split("-")
    if len(parts) >= 2:
        return LUNI_RO.get(parts[1], parts[1])
    return luna_str


def mascheaza_email(email: str) -> str:
    """Maschează email-ul păstrând prima literă și domeniul.

    'cnecrea@gmail.com' → 'c******@gmail.com'
    """
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}@{domain}"
