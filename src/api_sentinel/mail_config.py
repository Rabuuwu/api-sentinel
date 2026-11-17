"""Conservative email validation; ASCII addresses only, no display names or headers."""

import re


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if (
        len(value) > 254
        or not re.fullmatch(
            r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value
        )
        or ".." in value
        or len(value.split("@")[0]) > 64
    ):
        raise ValueError("Enter a valid email address")
    local, domain = value.split("@")
    if (
        local.startswith(".")
        or local.endswith(".")
        or any(
            len(label) > 63 or label.startswith("-") or label.endswith("-")
            for label in domain.split(".")
        )
    ):
        raise ValueError("Enter a valid email address")
    return value
