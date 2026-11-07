"""Where the project's files live: config, docs, eval, security, data.

From a source checkout or an editable install this is the repository root. A container or any
other install sets ``FACTORY_ENERGY_HOME`` to the folder that holds ``config/`` and ``docs/``.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("FACTORY_ENERGY_HOME") or Path(__file__).resolve().parents[2])
CONFIG_DIR = ROOT / "config"
