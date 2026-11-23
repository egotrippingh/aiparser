"""Validation for external images shown in saved answers."""

import ipaddress
from urllib.parse import urlsplit


def image_url(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 2000 or any(ord(char) < 32 for char in value):
        return ""
    try:
        url = urlsplit(value.strip())
    except ValueError:
        return ""
    host = (url.hostname or "").rstrip(".")
    if url.scheme != "https" or url.username is not None or url.password is not None or "." not in host or host.endswith((".localhost", ".local")):
        return ""
    try:
        if not ipaddress.ip_address(host).is_global:
            return ""
    except ValueError:
        if host.rsplit(".", 1)[-1].isdecimal():  # Browsers accept abbreviated and legacy numeric host formats.
            return ""
    return value.strip()
