from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.iptv_multi_source import analyze_source_url, scope_value_counts, validate_reports, validate_source_workflow


def validate_gui_contract(repo_root: Path) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    gui_path = repo_root / "scripts" / "iptv_multi_source_gui.py"
    text = gui_path.read_text(encoding="utf-8")
    forbidden_phrases = [
        "not available yet",
        "Show redacted URLs",
        "Show local dataset status",
        "Parse selected",
        "Load report summary",
        "Fetch Xtream API metadata",
    ]
    for phrase in forbidden_phrases:
        if phrase in text:
            errors.append(f"forbidden_gui_phrase:{phrase}")
    required_phrases = [
        "Run Full Inventory",
        "Analyze URL",
        "View Safe URLs",
        "View Source Status",
        "Fetch All Source Data",
        "Fetch Channel/Movie/Series Metadata",
        "Parse Inventory",
        "Groups / Categories",
        "Build Source Filters from Actual Values",
    ]
    for phrase in required_phrases:
        if phrase not in text:
            errors.append(f"required_gui_phrase_missing:{phrase}")
    return {"errors": errors, "warnings": warnings}


def validate_url_analysis() -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    result = analyze_source_url("https://cf.example-provider.test/get.php?username=user%40mail&password=pass%2Bword&type=m3u_plus&output=ts")
    expected = {
        "server_url": "https://cf.example-provider.test",
        "source_key": "example-provider",
        "source_display_name": "Example Provider",
        "source_type": "xtream_codes",
        "username": "user@mail",
        "password": "pass+word",
    }
    for key, value in expected.items():
        if result.get(key) != value:
            errors.append(f"url_analysis_mismatch:{key}:{result.get(key)}")
    for key in ("m3u_url", "epg_url", "api_base"):
        if not result.get(key):
            errors.append(f"url_analysis_missing:{key}")
    return {"errors": errors, "warnings": warnings}


def validate_scope_values(repo_root: Path, source_key: str) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not source_key:
        return {"errors": errors, "warnings": warnings}
    for field in ("group_title", "item_type", "country_normalized", "language_normalized", "network_normalized"):
        values = scope_value_counts(repo_root, source_key, field, "", 25)
        if not values and field in {"group_title", "item_type"}:
            errors.append(f"scope_values_missing:{source_key}:{field}")
        elif not values:
            warnings.append(f"scope_values_empty:{source_key}:{field}")
    return {"errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate multi-source IPTV parser workflow.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--source-key", default="")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    result = validate_source_workflow(repo_root, args.source_key or None)
    gui = validate_gui_contract(repo_root)
    url = validate_url_analysis()
    reports = validate_reports(repo_root, args.source_key) if args.source_key else {"ok": True, "errors": [], "warnings": []}
    scope = validate_scope_values(repo_root, args.source_key)
    result["errors"].extend(gui["errors"])
    result["errors"].extend(url["errors"])
    result["errors"].extend(reports["errors"])
    result["errors"].extend(scope["errors"])
    result["warnings"].extend(gui["warnings"])
    result["warnings"].extend(url["warnings"])
    result["warnings"].extend(reports["warnings"])
    result["warnings"].extend(scope["warnings"])
    result["ok"] = not result["errors"]
    result["gui_contract"] = gui
    result["url_analysis"] = url
    result["report_validation"] = reports
    result["scope_values"] = scope
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
