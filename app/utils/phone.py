from __future__ import annotations

import phonenumbers


def normalize_phone(value: str, region: str = "RU") -> str:
    parsed = phonenumbers.parse(value, region)
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

