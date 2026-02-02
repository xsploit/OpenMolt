"""
Thin wrapper around the official TOON Node package using npx.
We shell out instead of re-implementing the format.

Requirements:
- Node + npm on PATH.
- Internet access the first time to fetch @toon-format/cli; npm cache is used afterwards.

Usage:
    from toon_cli import encode_to_toon
    s = encode_to_toon({"hello": "world"})
"""

import json
import subprocess
from typing import Any, Optional

NPX_CMD = ["npx", "--yes", "@toon-format/cli"]


def encode_to_toon(obj: Any, timeout: int = 8) -> Optional[str]:
    """
    Encode a JSON-serializable object to TOON format using the official CLI.
    Returns the TOON string, or None if the CLI fails.
    """
    try:
        proc = subprocess.run(
            NPX_CMD,
            input=json.dumps(obj).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=True,
        )
        return proc.stdout.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None


__all__ = ["encode_to_toon"]

