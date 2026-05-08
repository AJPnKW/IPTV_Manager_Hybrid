from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


KNOWN_UPPER = {
    "A&E",
    "ABC", "AMC", "BBC", "CBC", "CBS", "CNN", "CP24", "CTV", "CTV2", "CW",
    "FOX", "HBO", "HGTV", "MLB", "MNT", "MSNBC", "MTV", "NBC", "NFL",
    "NHL", "PBS", "SBS", "TLC", "TMN", "TV", "UK", "US",
}
NETWORKS = {
    "ABC", "BBC", "CBC", "CBS", "Citytv", "CTV", "CTV2", "CW", "FOX",
    "Global", "MNT", "NBC", "PBS", "Rogers TV",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def esc_attr(value: str) -> str:
    return html.escape(value or "", quote=True)


def clean_token_text(value: str) -> str:
    value = value or ""
    value = value.replace("\ufeff", "").replace("ï¿", "").replace("◉", "")
    value = re.sub(r"\b(alliptvlinks\.com|geo-blocked|not 24/7)\b", " ", value, flags=re.I)
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\bbackup\s*no[_ -]*\d+\b", " ", value, flags=re.I)
    value = re.sub(r"\bno[_ -]*\d+\b", " ", value, flags=re.I)
    value = re.sub(r"^\s*[\|\[]?(CA|US|UK|AU)[\]\|]?\s*[-:|]?\s*", " ", value, flags=re.I)
    value = re.sub(r"\b(4K|UHD|FHD|HD|SD|1080p|720p|540p|480p)\b", " ", value, flags=re.I)
    value = re.sub(r"\(\s*\)", " ", value)
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -|:")


def title_channel(value: str) -> str:
    value = value.replace("&e", "&E").replace("&E", "&E")
    words = []
    for word in re.split(r"(\s+)", value.strip()):
        if not word or word.isspace():
            words.append(word)
            continue
        raw = word.strip("()")
        upper = raw.upper()
        if upper in KNOWN_UPPER:
            words.append(word.replace(raw, upper))
        elif re.search(r"\d", raw) and re.search(r"[a-zA-Z]", raw):
            words.append(word.replace(raw, upper))
        elif re.fullmatch(r"[A-Z]{3,5}", raw):
            words.append(word)
        else:
            words.append(word.lower().capitalize())
    return "".join(words).strip()


def normalize_network(network: str, name: str) -> str:
    text = f" {network} {name} ".lower()
    checks = [
        ("Rogers TV", ["rogers tv"]),
        ("CTV2", ["ctv2", "ctv 2", "ctv two"]),
        ("CTV", ["ctv"]),
        ("CBC", ["cbc"]),
        ("Global", ["global"]),
        ("Citytv", ["citytv"]),
        ("ABC", ["abc"]),
        ("CBS", ["cbs"]),
        ("NBC", ["nbc"]),
        ("FOX", ["fox"]),
        ("CW", [" cw ", "wnlo"]),
        ("PBS", ["pbs"]),
        ("BBC", ["bbc"]),
        ("SBS", ["sbs"]),
    ]
    for value, patterns in checks:
        if any(pattern in text for pattern in patterns):
            return value
    return network or ""


def normalize_name(item: dict) -> str:
    original = item.get("name") or ""
    raw = clean_token_text(original)
    network = normalize_network(item.get("network", ""), raw)
    city = item.get("city") or ""
    call = item.get("call") or item.get("callLetters") or ""
    category = item.get("category") or ""

    crave_match = re.search(r"(?:TMN\s*)?(\d)?\s*\(?\s*CRAVE(?:\s*TV)?\s*(\d)?", original, re.I)
    if crave_match:
        number = crave_match.group(2) or crave_match.group(1) or ""
        return f"Crave {number}".strip()

    if network in NETWORKS and city:
        if item.get("country") == "US" and call:
            return f"{network} {city} {call}"
        return f"{network} {city}"

    if network and raw.lower() in {network.lower(), f"{network.lower()} channel"} and city:
        return f"{network} {city}"

    raw = re.sub(r"\bCTV\s*2\b", "CTV2", raw, flags=re.I)
    raw = re.sub(r"\bA\s*&\s*E\b", "A&E", raw, flags=re.I)
    raw = re.sub(r"\bVIP\b", " ", raw, flags=re.I)
    raw = re.sub(r"\(\s*\)", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw and network:
        raw = network
    if category == "FAST" and network and network.lower() not in raw.lower():
        raw = f"{network} {raw}".strip()
    return title_channel(raw)


def canonical_key(item: dict, display_name: str) -> str:
    country = item.get("country") or ""
    network = normalize_network(item.get("network", ""), display_name)
    city = item.get("city") or ""
    call = item.get("call") or item.get("callLetters") or ""
    if call:
        return f"{country}|CALL|{call.upper()}"
    if network and city:
        return f"{country}|NETCITY|{network.lower()}|{city.lower()}"
    return f"{country}|NAME|{re.sub(r'[^a-z0-9]+', ' ', display_name.lower()).strip()}"


def group_title(item: dict) -> str:
    country = item.get("country") or "UN"
    category = item.get("category") or "General"
    network = normalize_network(item.get("network", ""), item.get("name", ""))
    if category == "Local":
        return f"{country} | Local"
    if network in NETWORKS and item.get("city"):
        return f"{country} | Local"
    return f"{country} | {category}"


def choose_group(group: list[dict]) -> str:
    groups = [group_title(row) for row in group]
    for preferred in ["Local", "News", "Documentary", "Movies", "Kids", "Lifestyle", "FAST", "General"]:
        for group_title_value in groups:
            if group_title_value.endswith(f"| {preferred}"):
                return group_title_value
    return groups[0] if groups else "UN | General"


def tvg_id_for(item: dict, display_name: str, alt_index: int) -> str:
    existing = item.get("tvgId") or item.get("tvg_id") or ""
    if existing:
        return existing
    base = re.sub(r"[^a-z0-9]+", ".", display_name.lower()).strip(".")
    country = (item.get("country") or "").lower()
    suffix = f".alt{alt_index:02d}" if alt_index else ""
    return f"{base}.{country}{suffix}".strip(".")


def load_keep_items(decisions_path: Path, records_path: Path | None) -> list[dict]:
    decisions = load_json(decisions_path).get("decisions", [])
    records_by_id = {}
    if records_path and records_path.exists():
        for record in load_json(records_path):
            records_by_id[record.get("review_id")] = record

    items = []
    for decision in decisions:
        if (decision.get("manualDecision") or decision.get("decision")) != "keep":
            continue
        merged = {**records_by_id.get(decision.get("id"), {}), **decision}
        if not merged.get("streamUrl") and merged.get("source_stream_url"):
            merged["streamUrl"] = merged["source_stream_url"]
        if not merged.get("name") and merged.get("source_record_name"):
            merged["name"] = merged["source_record_name"]
        if not merged.get("call") and merged.get("call_letters"):
            merged["call"] = merged["call_letters"]
        if merged.get("streamUrl"):
            items.append(merged)
    return items


def build_outputs(items: list[dict]) -> tuple[list[dict], list[dict]]:
    by_url = {}
    for item in items:
        by_url.setdefault(item["streamUrl"], item)

    rows = []
    for item in by_url.values():
        display = normalize_name(item)
        key = canonical_key(item, display)
        rows.append({**item, "normalizedNameBase": display, "canonicalKey": key})

    rows.sort(key=lambda row: (row.get("country", ""), group_title(row), row["normalizedNameBase"], row.get("streamUrl", "")))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["canonicalKey"]].append(row)

    output_rows = []
    qa_rows = []
    for key, group in grouped.items():
        selected_group = choose_group(group)
        for index, row in enumerate(group):
            alt_index = index if len(group) > 1 else 0
            suffix = f" ALT{index:02d}" if index else ""
            output_name = f"{row['normalizedNameBase']}{suffix}"
            out = {
                **row,
                "outputName": output_name,
                "outputGroup": selected_group,
                "outputTvgId": tvg_id_for(row, row["normalizedNameBase"], alt_index),
                "alternateIndex": alt_index,
                "alternateCount": len(group),
            }
            output_rows.append(out)
        if len(group) > 1:
            qa_rows.append({
                "canonicalKey": key,
                "normalizedName": group[0]["normalizedNameBase"],
                "alternateCount": len(group),
                "streams": [row.get("streamUrl", "") for row in group],
                "sourceNames": [row.get("name", "") for row in group],
            })
    return output_rows, qa_rows


def render_m3u(rows: list[dict]) -> str:
    lines = ["#EXTM3U"]
    for row in rows:
        logo = row.get("source_logo_url") or row.get("logo") or ""
        attrs = [
            f'tvg-id="{esc_attr(row["outputTvgId"])}"',
            f'tvg-name="{esc_attr(row["outputName"])}"',
            f'group-title="{esc_attr(row["outputGroup"])}"',
        ]
        if logo:
            attrs.append(f'tvg-logo="{esc_attr(logo)}"')
        lines.append(f'#EXTINF:-1 {" ".join(attrs)},{row["outputName"]}')
        lines.append(row["streamUrl"])
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "outputName", "normalizedNameBase", "outputGroup", "country", "category", "network",
        "owner", "city", "region", "call", "stationClass", "alternateIndex",
        "alternateCount", "streamUrl", "name", "sourceFile",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_html_report(rows: list[dict], qa_rows: list[dict]) -> str:
    country_counts = Counter(row.get("country", "") for row in rows)
    group_counts = Counter(row.get("outputGroup", "") for row in rows)
    stat_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in sorted(country_counts.items()))
    group_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in sorted(group_counts.items()))
    qa_table = "".join(
        f"<tr><td>{html.escape(row['normalizedName'])}</td><td>{row['alternateCount']}</td><td>{html.escape('; '.join(row['sourceNames'][:8]))}</td></tr>"
        for row in qa_rows[:500]
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>TiviMate Output Report</title>
<style>body{{font-family:Verdana,Arial,sans-serif;margin:16px;background:#f7f3eb;color:#1b2421}}table{{border-collapse:collapse;width:100%;background:white;margin:10px 0}}td,th{{border:1px solid #ccc;padding:5px;text-align:left}}th{{background:#e6ded0}}</style></head>
<body><h1>TiviMate Output Report</h1><p>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}. Output channels: {len(rows)}. Alternate groups: {len(qa_rows)}.</p>
<h2>Countries</h2><table><tbody>{stat_rows}</tbody></table><h2>Groups</h2><table><tbody>{group_rows}</tbody></table>
<h2>Alternate Channel QA</h2><table><thead><tr><th>Normalized Channel</th><th>Streams</th><th>Source Names</th></tr></thead><tbody>{qa_table}</tbody></table></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build normalized TiviMate-ready M3U outputs from reviewed keep decisions.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--decisions", type=Path, default=Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid\ouput\m3u_candidate_review_decisions.json"))
    parser.add_argument("--records", type=Path, default=Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid\data\m3u_scope_candidates.records.json"))
    parser.add_argument("--out-dir", type=Path, default=Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid\ouput"))
    args = parser.parse_args()

    items = load_keep_items(args.decisions, args.records)
    rows, qa_rows = build_outputs(items)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    master = args.out_dir / "tivimate_reviewed_normalized_master.m3u"
    master.write_text(render_m3u(rows), encoding="utf-8")

    for country in sorted({row.get("country") or "UN" for row in rows}):
        subset = [row for row in rows if (row.get("country") or "UN") == country]
        (args.out_dir / f"tivimate_reviewed_normalized_{country}.m3u").write_text(render_m3u(subset), encoding="utf-8")

    write_csv(args.out_dir / "tivimate_reviewed_normalized_channels.csv", rows)
    (args.out_dir / "tivimate_reviewed_alternate_groups.json").write_text(json.dumps(qa_rows, indent=2), encoding="utf-8")
    (args.out_dir / "tivimate_reviewed_output_report.html").write_text(render_html_report(rows, qa_rows), encoding="utf-8")

    print(f"Keep decisions loaded: {len(items)}")
    print(f"Output streams: {len(rows)}")
    print(f"Alternate groups: {len(qa_rows)}")
    print(master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
