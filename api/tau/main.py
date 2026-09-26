"""Thin ASGI entrypoint for the optional Tau runtime.

The deployer selects tool sources through Tau process settings.
"""

from ms_tau_sdk import create_app

app = create_app()
