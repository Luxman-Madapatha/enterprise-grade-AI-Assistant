"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable when running pytest from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
