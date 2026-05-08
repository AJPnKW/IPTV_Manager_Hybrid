from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def parse_extinf(line: str) -> dict:
    if "," in line:
        left, name = line.split(",", 1)
    else:
        left, name = line, ""
    return {
        "name": name.strip(),
        "attrs": dict(ATTR_RE.findall(left)),
    }


def inventory_m3u_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("#EXTINF"):
            parsed = parse_extinf(line)
            stream_url = ""
            if idx + 1 < len(lines) and not lines[idx + 1].startswith("#"):
                stream_url = lines[idx + 1]
            entries.append({
                "name": parsed["name"],
                "stream_url": stream_url,
                "tvg_id": parsed["attrs"].get("tvg-id", ""),
                "tvg_name": parsed["attrs"].get("tvg-name", ""),
                "group_title": parsed["attrs"].get("group-title", ""),
                "tvg_logo": parsed["attrs"].get("tvg-logo", ""),
            })
            idx += 2
        else:
            idx += 1

    groups = Counter(entry["group_title"] or "(none)" for entry in entries)
    urls = Counter(entry["stream_url"] for entry in entries if entry["stream_url"])
    return {
        "path": str(path),
        "file_name": path.name,
        "bytes": path.stat().st_size,
        "entry_count": len(entries),
        "unique_stream_url_count": len(urls),
        "duplicate_stream_url_count": sum(count - 1 for count in urls.values() if count > 1),
        "top_groups": groups.most_common(20),
        "sample_entries": entries[:10],
    }


def inventory_xmltv_file(path: Path) -> dict:
    channel_count = 0
    programme_count = 0
    channel_ids = []
    try:
        for event, elem in ET.iterparse(path, events=("end",)):
            if elem.tag == "channel":
                channel_count += 1
                channel_ids.append(elem.attrib.get("id", ""))
                elem.clear()
            elif elem.tag == "programme":
                programme_count += 1
                elem.clear()
    except ET.ParseError as exc:
        return {
            "path": str(path),
            "file_name": path.name,
            "bytes": path.stat().st_size,
            "parse_error": str(exc),
            "channel_count": 0,
            "programme_count": 0,
            "sample_channel_ids": [],
        }
    return {
        "path": str(path),
        "file_name": path.name,
        "bytes": path.stat().st_size,
        "channel_count": channel_count,
        "programme_count": programme_count,
        "sample_channel_ids": channel_ids[:20],
    }


def render_html(report: dict) -> str:
    m3u_rows = "\n".join(
        f"<tr><td>{item['file_name']}</td><td>{item['entry_count']}</td><td>{item['unique_stream_url_count']}</td><td>{item['duplicate_stream_url_count']}</td><td>{item['bytes']}</td></tr>"
        for item in report["m3u_files"]
    )
    xml_rows = "\n".join(
        f"<tr><td>{item['file_name']}</td><td>{item.get('channel_count', 0)}</td><td>{item.get('programme_count', 0)}</td><td>{item['bytes']}</td><td>{item.get('parse_error', '')}</td></tr>"
        for item in report["xmltv_files"]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IPTV Input Inventory</title>
  <style>
    body {{ margin:0; font-family:"Segoe UI",Tahoma,sans-serif; background:#f4efe7; color:#172126; }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:24px 18px 44px; }}
    .panel {{ background:#fffdf8; border:1px solid #d7cdbf; border-radius:18px; padding:20px; margin:0 0 18px; box-shadow:0 16px 36px rgba(23,33,38,.08); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
    .card {{ background:linear-gradient(135deg,#0b617e,#2389ab); color:white; border-radius:16px; padding:14px; }}
    .label {{ font-size:.76rem; text-transform:uppercase; letter-spacing:.08em; opacity:.88; }}
    .value {{ margin-top:8px; font-size:1.9rem; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ text-align:left; padding:10px; border-bottom:1px solid #d7cdbf; vertical-align:top; }}
    th {{ background:#ece4d8; font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <h1>IPTV Input Inventory</h1>
      <p>Generated at {report['generated_at']}.</p>
      <div class="grid">
        <div class="card"><div class="label">M3U Files</div><div class="value">{len(report['m3u_files'])}</div></div>
        <div class="card"><div class="label">M3U Entries</div><div class="value">{report['summary']['m3u_entry_count']}</div></div>
        <div class="card"><div class="label">XMLTV Files</div><div class="value">{len(report['xmltv_files'])}</div></div>
        <div class="card"><div class="label">XMLTV Channels</div><div class="value">{report['summary']['xmltv_channel_count']}</div></div>
      </div>
    </section>
    <section class="panel">
      <h2>M3U Files</h2>
      <table><thead><tr><th>File</th><th>Entries</th><th>Unique URLs</th><th>Duplicate URLs</th><th>Bytes</th></tr></thead><tbody>{m3u_rows}</tbody></table>
    </section>
    <section class="panel">
      <h2>XMLTV Files</h2>
      <table><thead><tr><th>File</th><th>Channels</th><th>Programmes</th><th>Bytes</th><th>Error</th></tr></thead><tbody>{xml_rows}</tbody></table>
    </section>
  </div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory local IPTV M3U and XMLTV input sources.")
    parser.add_argument("--m3u-dir", type=Path, default=Path(r"C:\Users\andrew\PROJECTS\iptv\collections\inputs_for_tivimate\m3u"))
    parser.add_argument("--xmltv-dir", type=Path, default=Path(r"C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting\IPTV"))
    parser.add_argument("--reports-dir", type=Path, default=Path(__file__).resolve().parents[1] / "reports")
    args = parser.parse_args()

    m3u_files = [inventory_m3u_file(path) for path in sorted(args.m3u_dir.glob("**/*")) if path.is_file() and path.suffix.lower() in {".m3u", ".m3u8"}]
    xmltv_names = [
        "Broadcast_LosAngeles_CA_US_xmltv_10272.xml",
        "Rogers_Toronto_ON_CA_xmltv_10270.xml",
        "Telus_Optik_Vancouver_BC_CA_xmltv_10269.xml",
        "Verizon_FIOS_NewYork_NY_US_xmltv_10273.xml",
        "Xfinity_Chicago_IL_US_xmltv_10271.xml",
    ]
    xmltv_files = [inventory_xmltv_file(args.xmltv_dir / name) for name in xmltv_names if (args.xmltv_dir / name).exists()]
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dirs": {
            "m3u_dir": str(args.m3u_dir),
            "xmltv_dir": str(args.xmltv_dir),
        },
        "summary": {
            "m3u_entry_count": sum(item["entry_count"] for item in m3u_files),
            "m3u_unique_stream_url_count": sum(item["unique_stream_url_count"] for item in m3u_files),
            "m3u_duplicate_stream_url_count": sum(item["duplicate_stream_url_count"] for item in m3u_files),
            "xmltv_channel_count": sum(item.get("channel_count", 0) for item in xmltv_files),
            "xmltv_programme_count": sum(item.get("programme_count", 0) for item in xmltv_files),
        },
        "m3u_files": m3u_files,
        "xmltv_files": xmltv_files,
    }
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    (args.reports_dir / "input_inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.reports_dir / "input_inventory.html").write_text(render_html(report), encoding="utf-8")
    print(f"Wrote {args.reports_dir / 'input_inventory.json'}")
    print(f"Wrote {args.reports_dir / 'input_inventory.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
