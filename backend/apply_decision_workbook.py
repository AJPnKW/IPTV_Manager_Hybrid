from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def answer(answers: dict, key: str, default: str = "dont_know") -> str:
    return (answers.get(key) or {}).get("answer") or default


def notes(answers: dict, key: str) -> str:
    return (answers.get(key) or {}).get("notes") or ""


def build_active_policy(seed_policy: dict, workbook: dict) -> dict:
    answers = workbook.get("answers", {})
    active = dict(seed_policy)
    active["version"] = "0.2-active"
    active["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active["generated_from"] = "input/iptv_decision_workbook_answers.json"
    active["workbook_exported_at"] = workbook.get("exported_at", "")

    active["target_countries"] = ["CA", "US", "UK", "AU"] if answer(answers, "target_countries") == "ca_us_uk_au" else ["CA", "US"]
    active["default_language"] = "English"
    active["language_policy"] = {
        "answer": answer(answers, "language_policy"),
        "decision": "exclude_non_english_by_default",
    }
    active["category_policy"] = {
        "sports": answer(answers, "sports_policy"),
        "religion": "exclude_default",
        "government": "exclude_default",
        "adult": "exclude_default",
        "foreign_content": "exclude_default",
        "notes": notes(answers, "target_countries"),
    }
    active["fast_policy"] = {
        "answer": answer(answers, "fast_policy"),
        "include_providers": ["Pluto", "Plex"],
        "exclude_providers": ["Samsung TV Plus", "Rakuten"],
        "notes": notes(answers, "fast_policy"),
    }
    active["provider_lineup_policy"] = {
        "answer": answer(answers, "provider_lineups"),
        "keep_source_files_intact": True,
        "reason": "Daily subscribed pulls are source-of-truth inputs and should be filtered downstream.",
    }
    active["dedupe_policy"] = {
        "m3u_unique_key": ["stream_url"],
        "xmltv_unique_key": ["source_lineup_id", "source_channel_id"],
        "same_channel_different_source": "keep_as_alternate",
        "same_stream_url_duplicate": "merge_metadata",
        "answer": answer(answers, "duplicate_policy"),
    }
    active["alternate_label_policy"] = {
        "style": answer(answers, "alternate_suffix", "ALT01"),
        "first_alternate": "ALT01",
        "examples": ["CTV Toronto", "CTV Toronto ALT01", "CTV Toronto ALT02"],
    }
    active["output_segmentation"] = {
        "answer": answer(answers, "output_segmentation"),
        "mode": "country_category",
        "examples": ["CA_Local.m3u", "US_News.m3u", "UK_General.m3u", "AU_General.m3u"],
    }
    active["exclude_keywords"] = sorted(set(
        active.get("exclude_rules", [])[1].get("keywords", [])
        + [
            "church", "religion", "religious", "faith", "god", "bible", "gospel",
            "parliament", "senate", "government", "legislature", "assembly",
            "foreign", "international", "world language"
        ]
    ))
    return active


def build_source_registry() -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    xmltv_root = Path(r"C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting\IPTV")
    m3u_root = Path(r"C:\Users\andrew\PROJECTS\iptv\collections\inputs_for_tivimate\m3u")
    return {
        "version": "0.1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_groups": [
            {
                "source_group_id": "local_m3u_collection",
                "type": "m3u_directory",
                "path": str(m3u_root),
                "role": "candidate_stream_sources",
                "policy": "inventory_then_scope_filter",
            },
            {
                "source_group_id": "subscribed_xmltv_provider_pulls",
                "type": "xmltv_files",
                "path": str(xmltv_root),
                "role": "authoritative_epg_sources",
                "policy": "keep_source_files_intact_filter_downstream",
                "files": [
                    "Broadcast_LosAngeles_CA_US_xmltv_10272.xml",
                    "Rogers_Toronto_ON_CA_xmltv_10270.xml",
                    "Telus_Optik_Vancouver_BC_CA_xmltv_10269.xml",
                    "Verizon_FIOS_NewYork_NY_US_xmltv_10273.xml",
                    "Xfinity_Chicago_IL_US_xmltv_10271.xml",
                ],
            },
            {
                "source_group_id": "curated_extended_input_reference",
                "type": "html_reference",
                "path": r"C:\Users\andrew\PROJECTS\iptv\temp\XTENDED IPTV MASTER SECTIONS.html",
                "role": "curated_uk_au_scope_reference",
                "policy": "parse_to_review_then_scope_outputs",
            },
            {
                "source_group_id": "prior_scope_outputs",
                "type": "generated_reference",
                "path": str(xmltv_root / "scope_outputs"),
                "role": "current_seeded_country_scope_outputs",
                "policy": "use_as_seed_not_final_truth",
            },
        ],
        "publish_targets": [
            {
                "target_id": "hp920_lan",
                "base_url": "http://192.168.1.73:8011/iptv-epg/",
                "role": "local_network_tivimate_access",
            },
            {
                "target_id": "github",
                "base_url": "https://github.com/AJPnKW/get_xmltvlisting/tree/main/IPTV",
                "role": "versioned_remote_reference",
            },
        ],
        "manager_repo": str(repo_root),
    }


def render_report(policy: dict, source_registry: dict) -> str:
    countries = ", ".join(policy["target_countries"])
    fast_include = ", ".join(policy["fast_policy"]["include_providers"])
    fast_exclude = ", ".join(policy["fast_policy"]["exclude_providers"])
    source_rows = "\n".join(
        f"<tr><td>{item['source_group_id']}</td><td>{item['type']}</td><td>{item['role']}</td><td><code>{item['path']}</code></td></tr>"
        for item in source_registry["source_groups"]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Applied IPTV Workbook Policy</title>
  <style>
    body {{ margin:0; font-family:"Segoe UI",Tahoma,sans-serif; background:#f4efe7; color:#172126; }}
    .wrap {{ max-width:1180px; margin:0 auto; padding:24px 18px 44px; }}
    .panel {{ background:#fffdf8; border:1px solid #d7cdbf; border-radius:18px; padding:20px; margin:0 0 18px; box-shadow:0 16px 36px rgba(23,33,38,.08); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
    .card {{ background:linear-gradient(135deg,#0b617e,#2389ab); color:white; border-radius:16px; padding:14px; }}
    .label {{ font-size:.76rem; text-transform:uppercase; letter-spacing:.08em; opacity:.88; }}
    .value {{ margin-top:8px; font-size:1.4rem; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ text-align:left; vertical-align:top; padding:10px; border-bottom:1px solid #d7cdbf; }}
    th {{ background:#ece4d8; text-transform:uppercase; letter-spacing:.05em; font-size:.78rem; }}
    code {{ background:#efe7dc; padding:2px 5px; border-radius:6px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <h1>Applied IPTV Workbook Policy</h1>
      <p>This report converts your workbook answers into concrete build policy.</p>
      <div class="grid">
        <div class="card"><div class="label">Countries</div><div class="value">{countries}</div></div>
        <div class="card"><div class="label">Language</div><div class="value">English only</div></div>
        <div class="card"><div class="label">Alternates</div><div class="value">{policy['alternate_label_policy']['style']}</div></div>
        <div class="card"><div class="label">M3U Dedupe</div><div class="value">Same stream URL only</div></div>
      </div>
    </section>
    <section class="panel">
      <h2>Scope Decisions</h2>
      <table>
        <tbody>
          <tr><th>Exclude</th><td>Sports, religion, government, adult, clearly non-English, foreign/non-target content.</td></tr>
          <tr><th>FAST</th><td>Include candidates from {fast_include}; exclude {fast_exclude}; still review individual channels.</td></tr>
          <tr><th>Provider XMLTV</th><td>Keep provider source pulls intact. Filter and normalize downstream.</td></tr>
          <tr><th>Output Segmentation</th><td>Country and category segmented files.</td></tr>
        </tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Registered Source Groups</h2>
      <table><thead><tr><th>ID</th><th>Type</th><th>Role</th><th>Path</th></tr></thead><tbody>{source_rows}</tbody></table>
    </section>
  </div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply IPTV decision workbook answers to active policy files.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--answers", type=Path, default=Path(__file__).resolve().parents[1] / "input" / "iptv_decision_workbook_answers.json")
    args = parser.parse_args()

    seed = load_json(args.repo / "config" / "scope_policy.seed.json")
    workbook = load_json(args.answers)
    active_policy = build_active_policy(seed, workbook)
    source_registry = build_source_registry()

    write_json(args.repo / "config" / "scope_policy.active.json", active_policy)
    write_json(args.repo / "data" / "source_registry.json", source_registry)
    report_path = args.repo / "reports" / "applied_workbook_policy.html"
    report_path.write_text(render_report(active_policy, source_registry), encoding="utf-8")
    print(f"Wrote {args.repo / 'config' / 'scope_policy.active.json'}")
    print(f"Wrote {args.repo / 'data' / 'source_registry.json'}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
