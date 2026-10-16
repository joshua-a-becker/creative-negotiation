#!/usr/bin/env python3
"""Score one Community Make & Meet tutorial offer with the shared engine."""

from __future__ import annotations

import os


os.environ["SCORER_DEFAULT_SPACE"] = "tutorial"

from score_offer import main  # noqa: E402  (default must be selected before import)


if __name__ == "__main__":
    raise SystemExit(main())
