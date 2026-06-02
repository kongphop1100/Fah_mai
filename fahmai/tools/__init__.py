"""Shared low-level tool infrastructure."""
from fahmai.db import get_engine

# one shared engine for all tools (lazy pool)
ENGINE = get_engine()
