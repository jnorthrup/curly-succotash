"""Curly Succotash backend package.

This file exists solely to make the ``backend`` directory a proper
Python package so that tests and other consumers can import
``backend.*`` modules without needing special PYTHONPATH hacks.

The package exports are intentionally minimal; most modules live
under ``backend.src``. We include this initializer to avoid
``ModuleNotFoundError`` during pytest collection.
"""

# Expose the ``src`` subpackage directly for convenience.
from __future__ import annotations

# This import is lazy: it merely ensures ``backend.src`` is a
# recognized namespace package when ``backend`` is imported.
import importlib
import sys

if "backend.src" not in sys.modules:
    try:
        importlib.import_module("backend.src")
    except ImportError:
        # ``backend/src`` should contain an ``__init__.py`` of its own
        # (it does), so this should not fail in normal operation.
        pass

__all__ = ["src"]
