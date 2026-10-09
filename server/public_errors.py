"""Present operational errors without exposing the collection supplier."""

import re


_SUPPLIER = re.compile(r"xml\s*r(?:iver|eaver)", re.IGNORECASE)


def public_error(message):
    return _SUPPLIER.sub("сервис сбора", message) if isinstance(message, str) else message


def public_progress(value):
    if isinstance(value, str):
        return public_error(value)
    if isinstance(value, list):
        return [public_progress(item) for item in value]
    if isinstance(value, dict):
        return {key: public_progress(item) for key, item in value.items()}
    return value
