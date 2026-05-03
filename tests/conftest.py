# tests/conftest.py
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_models: mark test as needing real model weight files (skipped in CI without weights)",
    )
