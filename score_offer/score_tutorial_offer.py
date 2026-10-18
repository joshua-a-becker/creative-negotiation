#!/usr/bin/env python3
"""Run one tutorial offer through the same scorer used by the Creative Negotiations app."""

from __future__ import annotations

from score_offer import main


if __name__ == "__main__":
    # Keep tutorial selection local to this call; do not change a server's defaults.
    raise SystemExit(main(default_space="tutorial"))
