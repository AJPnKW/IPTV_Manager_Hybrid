from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.iptv_multi_source import validate_source_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate multi-source IPTV parser workflow.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--source-key", default="")
    args = parser.parse_args()
    result = validate_source_workflow(args.repo_root.resolve(), args.source_key or None)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
