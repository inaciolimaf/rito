"""Smoke test: garante que o pacote da aplicação importa sem erro."""

import app


def test_app_package_is_importable() -> None:
    assert app.__version__
