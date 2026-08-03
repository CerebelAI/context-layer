import importlib


def test_top_level_modules_import() -> None:
    for name in ("connectors", "knowledge", "server"):
        assert importlib.import_module(name)
