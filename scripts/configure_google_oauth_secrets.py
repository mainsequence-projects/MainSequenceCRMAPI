"""Replace one-time Google OAuth Secret placeholders with operator-pasted values.

Run from the API repository root with its authenticated .venv Python. Input is
read from the terminal without echo and is never written to a local file.
"""

from __future__ import annotations

from getpass import getpass
from time import sleep

from mainsequence.client import Secret

ENTRIES = (
    ("CRM_GOOGLE_OAUTH_CLIENT_ID", "PASTE_GOOGLE_OAUTH_CLIENT_ID", "Google OAuth client ID"),
    ("CRM_GOOGLE_OAUTH_CLIENT_SECRET", "PASTE_GOOGLE_OAUTH_CLIENT_SECRET", "Google OAuth client secret"),
)


def secret_text(record: Secret) -> str | None:
    value = record.value
    return value.get_secret_value() if hasattr(value, "get_secret_value") else value


def replace_placeholder(name: str, placeholder: str, value: str) -> None:
    for attempt in range(10):
        try:
            record = Secret.get_or_none(name=name)
            if record is not None:
                current = secret_text(record)
                if current == value:
                    print(f"{name}: configured")
                    return
                if current != placeholder:
                    raise RuntimeError(f"{name} already has another value; leaving it unchanged")
                record.delete()
            else:
                Secret.create(name=name, value=value, timeout=45)
        except RuntimeError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is not None and status < 500 and status not in (404, 409):
                raise RuntimeError(f"{name}: platform rejected the replacement (HTTP {status})") from None
            print(f"{name}: backend interrupted; checking current state again ({attempt + 1}/10)", flush=True)
            sleep(2)
    record = Secret.get_or_none(name=name)
    if record is not None and secret_text(record) == value:
        print(f"{name}: configured")
        return
    raise RuntimeError(f"{name}: replacement could not be verified; check its platform Secret record")


def main() -> None:
    values = []
    for name, _, label in ENTRIES:
        value = getpass(f"Paste {label}: ").strip()
        if not value or value.startswith("PASTE_GOOGLE_"):
            raise RuntimeError(f"{name} must contain the real Google value")
        if name.endswith("CLIENT_ID") and not value.endswith(".apps.googleusercontent.com"):
            raise RuntimeError("The Google OAuth client ID must end with .apps.googleusercontent.com")
        values.append(value)

    print("Checking and replacing the two placeholder Secret records…", flush=True)
    for (name, placeholder, _), value in zip(ENTRIES, values, strict=True):
        try:
            replace_placeholder(name, placeholder, value)
        except Exception as exc:
            print(f"{name}: replacement failed ({type(exc).__name__}); check the Secret record before retrying")
            raise SystemExit(1) from None

    print("Both Google OAuth Secrets are configured. Return to CRM and select Connect Google Contacts.")


if __name__ == "__main__":
    main()
