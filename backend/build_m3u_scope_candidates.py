from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
COUNTRY_RE = re.compile(r"(?:^|[_-])(ca|us|uk|au)(?:[_\.-]|$)", re.I)
CALL_RE = re.compile(r"\b([A-Z]{3,5}(?:-DT|-TV|-HD)?)\b")
MATRIX_DEFAULT = Path(r"C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting\IPTV\channel_name_matrix.csv")
DEFAULT_M3U_DIRS = [
    Path(r"C:\Users\andrew\PROJECTS\iptv\collections\inputs_for_tivimate\m3u"),
    Path(r"C:\X1_Share\IPTV_load_files\sources"),
    Path(r"C:\Users\andrew\PROJECTS\iptv\collections\repos_programs\IPTV-ChannelStudio\data\raw\inbox"),
    Path(r"C:\Users\andrew\PROJECTS\iptv\collections\repos_programs\IPTV-ChannelStudio\data\raw\Processed"),
    Path(r"C:\Users\andrew\PROJECTS\iptv\collections\repos_programs\IPTV-ChannelStudio\outputs\playlists"),
    Path(r"C:\Users\andrew\PROJECTS\iptv\collections\repos_programs\iptv__C42511BE\streams"),
    Path(r"C:\Users\andrew\PROJECTS\GitHub\M3U_Manager-v3"),
    Path(r"C:\Users\andrew\PROJECTS\GitHub\ZedTV-IPTV-Player-Recorder-Scraper"),
    Path(r"C:\Users\andrew\PROJECTS\GitHub\ZedTV-IPTV-Player-Recorder-Scraper-DEV"),
]

OWNER_BY_NETWORK = {
    "ABC": "The Walt Disney Company",
    "BBC": "British Broadcasting Corporation",
    "CBC": "CBC/Radio-Canada",
    "CBS": "Paramount Global",
    "CW": "Nexstar Media Group",
    "CITY": "Rogers Sports & Media",
    "CITYTV": "Rogers Sports & Media",
    "CTV": "Bell Media",
    "CTV2": "Bell Media",
    "FOX": "Fox Corporation",
    "GLOBAL": "Corus Entertainment",
    "ITV": "ITV plc",
    "NBC": "NBCUniversal",
    "PBS": "Public Broadcasting Service",
    "ROGERS": "Rogers Communications",
    "ROGERSTV": "Rogers Communications",
    "MYNETWORKTV": "Fox Corporation",
    "MNT": "Fox Corporation",
    "PLEX": "Plex",
    "PLUTO": "Paramount Global",
    "SBS": "Special Broadcasting Service",
    "SEVEN": "Seven West Media",
    "NINE": "Nine Entertainment",
    "TEN": "Paramount Global",
    "10": "Paramount Global",
}

NETWORK_PATTERNS = [
    ("BBC", ["bbc one", "bbc two", "bbc three", "bbc four", "bbc news", "cbbc", "cbeebies"]),
    ("ITV", ["itv1", "itv2", "itv3", "itv4", "stv", "utv"]),
    ("Channel 4", ["channel 4", " more4 ", " film4 ", " 4seven ", " e4 "]),
    ("Channel 5", ["channel 5", "5usa", "5star"]),
    ("ABC", ["abc tv", "abc news", " abc "]),
    ("CW", [" cw ", "wnlo"]),
    ("SBS", ["sbs", "viceland"]),
    ("Seven", ["7two", "7mate", "seven"]),
    ("Nine", ["9gem", "9go", "nine"]),
    ("10", ["10 bold", "10 peach", "network 10"]),
    ("CTV2", ["ctv2"]),
    ("CTV2", ["ctv 2", "ctv two"]),
    ("CTV", ["ctv"]),
    ("CBC", ["cbc"]),
    ("Global", ["global"]),
    ("Citytv", ["citytv", " city "]),
    ("FOX", [" fox "]),
    ("NBC", [" nbc "]),
    ("CBS", [" cbs "]),
    ("PBS", [" pbs "]),
    ("Rogers TV", ["rogers tv"]),
    ("Pluto", ["pluto"]),
    ("Plex", ["plex"]),
]

NETWORK_BY_CALL = {
    "WKBW": "ABC",
    "WIVB": "CBS",
    "WGRZ": "NBC",
    "WUTV": "FOX",
    "WNLO": "CW",
    "WNED": "PBS",
    "WNYO": "MyNetworkTV",
    "CFTO": "CTV",
    "CKCO": "CTV",
    "CJOH": "CTV",
    "CIVT": "CTV",
    "CBLT": "CBC",
    "CBHT": "CBC",
    "CIHF": "Global",
}

CITY_REGION_TZ = {
    "toronto": ("Toronto", "ON", "America/Toronto"),
    "vancouver": ("Vancouver", "BC", "America/Vancouver"),
    "los angeles": ("Los Angeles", "CA", "America/Los_Angeles"),
    "new york": ("New York", "NY", "America/New_York"),
    "chicago": ("Chicago", "IL", "America/Chicago"),
    "seattle": ("Seattle", "WA", "America/Los_Angeles"),
    "tacoma": ("Tacoma", "WA", "America/Los_Angeles"),
    "calgary": ("Calgary", "AB", "America/Edmonton"),
    "winnipeg": ("Winnipeg", "MB", "America/Winnipeg"),
    "halifax": ("Halifax", "NS", "America/Halifax"),
    "kitchener": ("Kitchener", "ON", "America/Toronto"),
    "london on": ("London", "ON", "America/Toronto"),
    "barrie": ("Barrie", "ON", "America/Toronto"),
    "ottawa": ("Ottawa", "ON", "America/Toronto"),
    "montreal": ("Montreal", "QC", "America/Toronto"),
    "sudbury": ("Sudbury", "ON", "America/Toronto"),
    "north bay": ("North Bay", "ON", "America/Toronto"),
    "windsor": ("Windsor", "ON", "America/Toronto"),
    "buffalo": ("Buffalo", "NY", "America/New_York"),
    "london": ("London", "", "Europe/London"),
    "sydney": ("Sydney", "NSW", "Australia/Sydney"),
    "melbourne": ("Melbourne", "VIC", "Australia/Melbourne"),
    "brisbane": ("Brisbane", "QLD", "Australia/Brisbane"),
    "perth": ("Perth", "WA", "Australia/Perth"),
    "adelaide": ("Adelaide", "SA", "Australia/Adelaide"),
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    return html.escape(str(value or ""), quote=True)


def clean_call(value: str) -> str:
    value = re.sub(r"[^A-Z0-9-]", "", (value or "").upper())
    value = re.sub(r"-(HD|SD|DT|TV)\d*$", "", value)
    return value


def strip_quality(value: str) -> str:
    value = re.sub(r"\b(4K|UHD|FHD|HD|SD|720p|1080p|540p|480p)\b", "", value or "", flags=re.I)
    value = re.sub(r"\s+-\s+Canada$", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" -")


def norm(value: str) -> str:
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", value or "")
    value = re.sub(r"\b(4k|uhd|fhd|hd|sd|720p|1080p|540p|480p)\b", " ", value, flags=re.I)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def parse_extinf(line: str) -> tuple[dict, str]:
    left, _, name = line.partition(",")
    return dict(ATTR_RE.findall(left)), name.strip()


def parse_m3u(path: Path) -> list[dict]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    records = []
    idx = 0
    while idx < len(lines):
        if lines[idx].startswith("#EXTINF"):
            attrs, name = parse_extinf(lines[idx])
            url = lines[idx + 1] if idx + 1 < len(lines) and not lines[idx + 1].startswith("#") else ""
            records.append({
                "source_file": str(path),
                "source_file_name": path.name,
                "source_record_name": name,
                "source_stream_url": url,
                "source_tvg_id": attrs.get("tvg-id", ""),
                "source_tvg_name": attrs.get("tvg-name", ""),
                "source_group_title": attrs.get("group-title", ""),
                "source_logo_url": attrs.get("tvg-logo", ""),
            })
            idx += 2
        else:
            idx += 1
    return records


def load_matrix(path: Path) -> dict:
    indexes = {"exact": {}, "call": {}, "channel_id": {}}
    if not path.exists():
        return indexes
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            for key in ["dn_1", "dn_2", "dn_3", "final_display_name"]:
                if norm(row.get(key, "")):
                    indexes["exact"].setdefault(norm(row.get(key, "")), row)
            network = norm(row.get("network_base", ""))
            if len(network) > 4:
                indexes["exact"].setdefault(network, row)
            if clean_call(row.get("call_sign", "")):
                indexes["call"].setdefault(clean_call(row.get("call_sign", "")), row)
            if norm(row.get("channel_id", "")):
                indexes["channel_id"].setdefault(norm(row.get("channel_id", "")), row)
    return indexes


def match_matrix(record: dict, indexes: dict) -> tuple[dict | None, str]:
    values = [record.get("source_tvg_id", ""), record.get("source_tvg_name", ""), record.get("source_record_name", "")]
    for value in values:
        key = norm(value)
        if key in indexes["channel_id"]:
            return indexes["channel_id"][key], "xmltv_matrix:channel_id"
        if key in indexes["exact"]:
            return indexes["exact"][key], "xmltv_matrix:exact_name"
    for value in CALL_RE.findall(" ".join(values)):
        call = clean_call(value)
        if not is_station_call_sign(call):
            continue
        if call in indexes["call"]:
            return indexes["call"][call], "xmltv_matrix:call_sign"
    return None, ""


def is_station_call_sign(call: str) -> bool:
    # Avoid false joins from generic all-caps names like USA, SET, NEWS, MOVIE.
    return len(call) >= 4 and call[0] in {"C", "K", "W"}


def infer_country(record: dict) -> str:
    text = " ".join([record["source_file_name"], record["source_record_name"], record["source_tvg_id"], record["source_group_title"]])
    match = COUNTRY_RE.search(record["source_file_name"])
    if match:
        return match.group(1).upper()
    lower = f" {text.lower()} "
    if re.search(r"\.(ca|canada)(?:@|\.|$)", lower):
        return "CA"
    if re.search(r"\.(us|usa)(?:@|\.|$)", lower):
        return "US"
    if re.search(r"\.(uk|gb)(?:@|\.|$)", lower):
        return "UK"
    if re.search(r"\.(au|australia)(?:@|\.|$)", lower):
        return "AU"
    if " canada" in lower or " ca " in lower:
        return "CA"
    if " united states" in lower or " usa" in lower or " us " in lower:
        return "US"
    if " united kingdom" in lower or " uk " in lower or "britain" in lower:
        return "UK"
    if " australia" in lower or " au " in lower:
        return "AU"
    return "UNKNOWN"


def infer_fast_provider(record: dict) -> str:
    text = f"{record['source_file_name']} {record['source_record_name']} {record['source_group_title']} {record['source_stream_url']}".lower()
    if "pluto" in text:
        return "Pluto"
    if "plex" in text:
        return "Plex"
    if "samsung" in text:
        return "Samsung TV Plus"
    if "rakuten" in text:
        return "Rakuten"
    return ""


def classify(record: dict, policy: dict) -> dict:
    country = infer_country(record)
    fast = infer_fast_provider(record)
    text = " ".join([record["source_file_name"], record["source_record_name"], record["source_tvg_id"], record["source_tvg_name"], record["source_group_title"]])
    decision = "review"
    reasons = []
    if country not in set(policy["target_countries"]):
        decision = "exclude"
        reasons.append("non_target_country")
    if any(word.lower() in text.lower() for word in policy.get("exclude_keywords", [])):
        decision = "exclude"
        reasons.append("excluded_keyword")
    if fast in policy["fast_policy"]["exclude_providers"]:
        decision = "exclude"
        reasons.append(f"fast_provider_excluded:{fast}")
    elif fast in policy["fast_policy"]["include_providers"] and decision != "exclude":
        reasons.append(f"fast_provider_allowed_for_review:{fast}")
    if country in set(policy["target_countries"]) and decision != "exclude":
        reasons.append("target_country_candidate")
    return {"decision": decision, "decision_reasons": reasons, "inferred_country": country, "fast_provider": fast}


def stream_host(url: str) -> str:
    return urlparse(url).netloc.lower() if url else ""


def stream_scheme(url: str) -> str:
    return urlparse(url).scheme.lower() if url else ""


def infer_network(text: str, row: dict | None) -> str:
    if row:
        for key in ["network_base", "brand_scope", "dn_1"]:
            if row.get(key):
                return strip_quality(row[key])
    lower = f" {text.lower()} "
    for call, network in NETWORK_BY_CALL.items():
        if call.lower() in lower:
            return network
    for network, patterns in NETWORK_PATTERNS:
        if any(pattern in lower for pattern in patterns):
            return network
    return ""


def infer_owner(network: str, fast: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "", (network or "").upper())
    if key in OWNER_BY_NETWORK:
        return OWNER_BY_NETWORK[key]
    if fast == "Pluto":
        return "Paramount Global"
    if fast == "Plex":
        return "Plex"
    if fast == "Samsung TV Plus":
        return "Samsung"
    if fast == "Rakuten":
        return "Rakuten"
    return OWNER_BY_NETWORK.get(key, "")


def timezone_for(city: str, region: str, country: str, source_file: str) -> str:
    text = f"{city} {region} {source_file}".lower()
    for key, (_, _, tz) in CITY_REGION_TZ.items():
        if key in text:
            return tz
    if country == "UK":
        return "Europe/London"
    if country == "AU":
        return "Australia/Sydney"
    if country in {"CA", "US"}:
        if any(token in text for token in ["vancouver", "losangeles", "los angeles", "_bc_", "_ca_us"]):
            return "America/Los_Angeles"
        if "chicago" in text or "_il_" in text:
            return "America/Chicago"
        if any(token in text for token in ["toronto", "newyork", "new york", "_on_", "_ny_"]):
            return "America/Toronto" if country == "CA" else "America/New_York"
    return ""


def infer_city_region_tz(text: str, country: str, row: dict | None, source_file: str) -> tuple[str, str, str]:
    if row and (row.get("city") or row.get("region")):
        city = (row.get("city") or "").strip()
        region = (row.get("region") or "").strip()
        return city, region, timezone_for(city, region, country, source_file)
    lower = text.lower()
    for key, (city, region, tz) in CITY_REGION_TZ.items():
        if key in lower:
            if key == "london" and country == "CA":
                return "London", "ON", "America/Toronto"
            return city, region, tz
    return "", "", timezone_for("", "", country, source_file)


def infer_category(text: str, fast: str) -> str:
    lower = text.lower()
    checks = [
        ("Sports", ["sport", "espn", "tsn", "golf", "racing", "nfl", "nba", "mlb", "nhl"]),
        ("News", ["news", "weather", "business", "finance"]),
        ("Local", ["local", "broadcast", "affiliate", "regional channels", "regional"]),
        ("Movies", ["movie", "film", "cinema", "cinevault"]),
        ("Kids", ["kids", "children", "cbbc", "cbeebies", "cartoon"]),
        ("Documentary", ["documentary", "history", "nature", "science"]),
        ("Lifestyle", ["home", "food", "travel", "lifestyle"]),
        ("Crime", ["crime", "murder", "detective"]),
        ("Religious", ["church", "faith", "gospel", "religion", "bible", "jewish", "tbn", "trinity"]),
        ("Government", ["government", "parliament", "legislature", "assembly", "senate"]),
    ]
    for category, words in checks:
        if any(word in lower for word in words):
            return category
    return "FAST" if fast else "General"


def infer_type(category: str, row: dict | None, fast: str) -> str:
    if row and row.get("channel_type"):
        return row["channel_type"].strip()
    if fast:
        return "FAST"
    if category == "Local":
        return "local"
    if category != "General":
        return "specialty"
    return "general"


def infer_call(record: dict, row: dict | None) -> str:
    if row and row.get("call_sign"):
        call = clean_call(row["call_sign"])
        return call if is_station_call_sign(call) else ""
    ignored = {"NEWS", "MOVIE", "MOVIES", "LIVE", "LOCAL", "SPORT", "SPORTS", "FHD", "UHD"}
    for value in CALL_RE.findall(" ".join([record["source_record_name"], record["source_tvg_id"], record["source_tvg_name"]])):
        call = clean_call(value)
        if call and call not in ignored and is_station_call_sign(call):
            return call
    return ""


def infer_resolution(record: dict, row: dict | None) -> str:
    if row and row.get("resolution"):
        return row["resolution"].strip()
    match = re.search(r"\b(4K|UHD|FHD|1080p|720p|540p|480p|HD|SD)\b", " ".join([record["source_record_name"], record["source_tvg_name"], record["source_group_title"]]), re.I)
    return match.group(1).upper() if match else ""


def infer_provider(record: dict, fast: str) -> str:
    if fast:
        return fast
    text = f"{record['source_file_name']} {record['source_stream_url']}".lower()
    for provider in ["Roku", "IPTV-Org", "GitHub"]:
        if provider.lower().replace("-", "") in text.replace("-", ""):
            return provider
    return ""


def clean_city(city: str, text: str) -> str:
    city = (city or "").strip()
    if city and len(city) <= 18 and "(" not in city:
        return city
    lower = f"{city} {text}".lower()
    for key, (known_city, _, _) in CITY_REGION_TZ.items():
        if key in lower:
            return known_city
    return city


def classify_station(text: str, row: dict | None, fast: str, category: str, call_letters: str) -> tuple[str, str]:
    lower = text.lower()
    if any(token in lower for token in [" radio", " iheartradio", " tunein", " music choice"]):
        return "Radio", "Radio"
    if fast:
        return "FAST", "Streaming"
    if call_letters and (row or {}).get("channel_type") == "local":
        return "Broadcast", "TV"
    if call_letters:
        return "Broadcast", "TV"
    if category == "Local" and any(token in lower for token in ["ctv", "cbc", "global", "abc", "cbs", "nbc", "fox", "cw", "pbs", "rogers tv"]):
        return "Broadcast", "TV"
    if any(token in lower for token in ["hbo", "crave", "showtime", "starz", "amc", "cnn", "tnt", "usa network"]):
        return "Cable", "TV"
    if row and row.get("channel_number"):
        return "Cable", "TV"
    if category == "FAST":
        return "FAST", "Streaming"
    if category in {"Movies", "News", "Kids", "Documentary", "Lifestyle", "Crime"}:
        return "Specialty", "TV"
    return "Other", "Unknown"


def enrich(record: dict, classification: dict, matrix: dict) -> dict:
    row, match = match_matrix(record, matrix)
    matrix_text = " ".join((row or {}).get(key, "") for key in ["dn_1", "dn_2", "dn_3", "network_base", "final_display_name"])
    text = " ".join([record["source_file_name"], record["source_record_name"], record["source_tvg_id"], record["source_tvg_name"], record["source_group_title"], record["source_stream_url"], matrix_text])
    country = classification["inferred_country"]
    fast = classification["fast_provider"]
    network = infer_network(text, row)
    city, region, tz = infer_city_region_tz(text, country, row, record["source_file_name"])
    city = clean_city(city, text)
    category = infer_category(text, fast)
    call_letters = infer_call(record, row)
    station_class, station_medium = classify_station(text, row, fast, category, call_letters)
    return {
        "network": network,
        "owner": infer_owner(network, fast),
        "country": country,
        "city": city,
        "region": region,
        "channel_type": infer_type(category, row, fast),
        "station_class": station_class,
        "station_medium": station_medium,
        "category": category,
        "call_letters": call_letters,
        "channel_number": (row or {}).get("channel_number", ""),
        "time_zone": tz,
        "resolution": infer_resolution(record, row),
        "source_provider": infer_provider(record, fast),
        "stream_host": stream_host(record["source_stream_url"]),
        "stream_scheme": stream_scheme(record["source_stream_url"]),
        "lineup_id": (row or {}).get("lineup_id", ""),
        "xmltv_channel_id": (row or {}).get("channel_id", ""),
        "metadata_match": match,
        "metadata_confidence": "high" if match else ("medium" if network or city or fast else "low"),
        "metadata_sources": ["m3u", "filename"] + ([match] if match else []),
    }


def canonical_seed(record: dict, classification: dict, metadata: dict, alt_style: str) -> dict:
    name = re.sub(r"\s+", " ", record["source_tvg_name"] or record["source_record_name"] or "Unknown").strip()
    return {
        "canonical_channel_id": "",
        "output_channel_name": name,
        "output_tvg_id": record["source_tvg_id"],
        "output_tvg_name": name,
        "output_group_title": f"{classification['inferred_country']} | {metadata.get('category') or 'Review'}",
        "output_country": classification["inferred_country"],
        "output_language": "English",
        "alternate_label_style": alt_style,
    }


def stable_review_id(record: dict) -> str:
    key = record.get("source_stream_url") or "|".join([
        record.get("source_file_name", ""),
        record.get("source_record_name", ""),
        record.get("source_tvg_id", ""),
    ])
    return "m3u-" + hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:12]


def record_quality(record: dict) -> int:
    text = " ".join([
        record.get("source_file_name", ""),
        record.get("source_record_name", ""),
        record.get("source_tvg_id", ""),
        record.get("source_group_title", ""),
    ]).lower()
    score = 0
    if record.get("source_tvg_id"):
        score += 5
    if record.get("source_group_title") and record.get("source_group_title", "").lower() != "undefined":
        score += 4
    if "x1_share" in record.get("source_file", "").lower() or "ca-iptv-file" in text or "consolidated_" in text:
        score += 8
    if any(token in text for token in ["kitchener", "london", "barrie", "halifax", "buffalo", "ctv", "abc", "cbs", "nbc", "fox", "cw"]):
        score += 6
    if infer_country(record) in {"CA", "US", "UK", "AU"}:
        score += 3
    return score


def merge_duplicate_record(existing: dict, candidate: dict) -> dict:
    source_files = set(existing.get("source_files", [existing.get("source_file", "")]))
    source_files.add(candidate.get("source_file", ""))
    aliases = set(existing.get("source_alias_names", [existing.get("source_record_name", "")]))
    aliases.add(candidate.get("source_record_name", ""))
    groups = set(existing.get("source_group_titles", [existing.get("source_group_title", "")]))
    groups.add(candidate.get("source_group_title", ""))
    winner = candidate if record_quality(candidate) > record_quality(existing) else existing
    merged = {**winner}
    merged["source_files"] = sorted(x for x in source_files if x)
    merged["source_alias_names"] = sorted(x for x in aliases if x)
    merged["source_group_titles"] = sorted(x for x in groups if x)
    merged["duplicate_source_count"] = len(merged["source_files"])
    return merged


def discover_m3u_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    skip_parts = {"__pycache__", ".git", "node_modules"}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("**/*")):
            if not path.is_file() or path.suffix.lower() not in {".m3u", ".m3u8"}:
                continue
            if any(part.lower() in skip_parts for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(path)
    return files


def load_prior_decisions(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for item in data.get("decisions", []):
        decision = item.get("manualDecision") or item.get("decision")
        if not decision:
            continue
        if item.get("streamUrl"):
            out["url:" + item["streamUrl"]] = {"decision": decision, "selected": item.get("selected", False), "note": item.get("note", "")}
        if item.get("name"):
            out["name:" + norm(item["name"])] = {"decision": decision, "selected": item.get("selected", False), "note": item.get("note", "")}
    return out


def prior_state_for_record(record: dict, prior: dict) -> dict:
    return prior.get("url:" + record.get("source_stream_url", "")) or prior.get("name:" + norm(record.get("source_record_name", ""))) or {}


def render_row(item: dict) -> str:
    name = item["source_tvg_name"] or item["source_record_name"]
    search = " ".join(str(item.get(k, "")) for k in ["decision", "country", "city", "region", "category", "network", "owner", "call_letters", "station_class", "station_medium", "source_file_name", "source_group_title", "stream_host"])
    search = f"{search} {name}".lower()
    return f"""<tr data-id="{esc(item['review_id'])}" data-decision="{esc(item['decision'])}" data-country="{esc(item['country'])}" data-category="{esc(item['category'])}" data-station-class="{esc(item['station_class'])}" data-search="{esc(search)}">
<td data-col="decision"><span class="pill decision-label {esc(item['decision'])}">{esc(item['decision'])}</span><button class="mini keep" title="Keep">K</button><button class="mini exclude" title="Exclude">X</button><button class="mini review" title="Review">R</button></td>
<td data-col="select"><input class="sel" type="checkbox"></td><td class="name" data-col="name" title="{esc(name)}">{esc(name)}</td><td data-col="call">{esc(item['call_letters'])}</td><td data-col="country">{esc(item['country'])}</td><td data-col="category">{esc(item['category'])}</td><td data-col="network">{esc(item['network'])}</td><td data-col="owner">{esc(item['owner'])}</td><td data-col="city">{esc(item['city'])}</td><td data-col="region">{esc(item['region'])}</td><td data-col="station_class">{esc(item['station_class'])}</td><td data-col="medium">{esc(item['station_medium'])}</td><td data-col="type">{esc(item['channel_type'])}</td><td data-col="timezone">{esc(item['time_zone'])}</td><td data-col="provider">{esc(item['source_provider'])}</td><td data-col="notes"><input class="note" placeholder="note"></td></tr>"""


def options(counter: dict) -> str:
    return "".join(f'<option value="{esc(key)}">{esc(key)} ({value})</option>' for key, value in sorted(counter.items()))


def render_html(report: dict, records: list[dict], initial_state: dict | None = None) -> str:
    review_records = [item for item in records if item["decision"] == "review"]
    embedded = json.dumps([{
        "id": item["review_id"],
        "decision": item["decision"],
        "name": item["source_tvg_name"] or item["source_record_name"],
        "call": item["call_letters"],
        "country": item["country"],
        "category": item["category"],
        "network": item["network"],
        "owner": item["owner"],
        "city": item["city"],
        "region": item["region"],
        "type": item["channel_type"],
        "stationClass": item["station_class"],
        "medium": item["station_medium"],
        "timeZone": item["time_zone"],
        "provider": item["source_provider"],
        "sourceFile": item["source_file_name"],
        "streamUrl": item["source_stream_url"],
        "search": " ".join(str(item.get(k, "")) for k in [
            "decision", "country", "city", "region", "category", "network", "owner",
            "call_letters", "station_class", "station_medium", "source_file_name",
            "source_group_title", "stream_host",
        ]).lower() + " " + (item["source_tvg_name"] or item["source_record_name"]).lower(),
    } for item in review_records], ensure_ascii=True)
    template = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>M3U Candidate Review Tool</title>
<style>
body{margin:0;font-family:Verdana,Arial,sans-serif;background:#f4f0e8;color:#17211f;overflow:hidden}.app{display:grid;grid-template-columns:196px 1fr;height:100vh;width:100vw}aside{background:#17211f;color:#f7efe4;padding:6px;border-right:2px solid #40504a;overflow:auto}main{min-width:0;padding:0;overflow:hidden}h1{font-size:15px;margin:2px 0 8px}label{display:block;font-size:10px;text-transform:uppercase;color:#b9c4bd;margin-top:7px}input,select,button{border:1px solid #9ca79f;border-radius:4px;padding:4px;font:12px Verdana,Arial,sans-serif}aside input,aside select,aside button{width:100%;margin-top:3px}select[multiple]{height:58px}button{cursor:pointer;background:#255b67;color:white}.side-row{display:grid;grid-template-columns:1fr 1fr;gap:4px}.stat{font-size:11px;color:#d7dfd8;margin:6px 0}.hint{font-size:10px;color:#9fb0a8;margin-top:2px}.table{height:calc(100vh - 26px);width:100%;overflow:auto;background:white}table{border-collapse:collapse;width:max-content;min-width:100%;font-size:11px;line-height:1.12}th,td{border:1px solid #d8d8d8;padding:2px 3px;text-align:left;vertical-align:middle;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}th{position:sticky;top:0;z-index:3;background:#e7dfd2;font-size:10px;text-transform:uppercase;padding:2px}th .head{display:flex;align-items:center;justify-content:space-between;gap:3px;cursor:pointer}th input,th select{width:100%;margin-top:2px;padding:1px;font-size:10px}tr:nth-child(even){background:#fafafa}tr:hover{background:#fff6d7}.pill{display:inline-block;border-radius:999px;padding:1px 5px;font-weight:bold}.review{background:#fff1cb;color:#8b5b00}.keep{background:#126b42!important;color:white}.exclude{background:#9b2f27!important;color:white}.mini{width:18px;padding:1px;margin-left:1px;font-size:10px;border-radius:3px}.selected{outline:2px solid #255b67;outline-offset:-2px}.topbar{height:26px;background:#fffdf8;border-bottom:1px solid #d8d8d8;display:flex;align-items:center;gap:5px;padding:2px 6px;font-size:11px}.topbar button,.topbar select{width:auto;padding:2px 6px}.note{width:92px;padding:1px;font-size:11px}#status{font-size:11px;color:#b9c4bd;margin-top:6px;min-height:38px}.name{font-weight:600}
[data-col=decision],th[data-sort=decision]{width:94px;max-width:94px}[data-col=select]{width:28px;max-width:28px}[data-col=name],th[data-sort=name]{width:230px;max-width:230px}[data-col=call],th[data-sort=call]{width:58px;max-width:58px}[data-col=country],th[data-sort=country]{width:36px;max-width:36px}[data-col=category],th[data-sort=category]{width:82px;max-width:82px}[data-col=network],th[data-sort=network]{width:150px;max-width:150px}[data-col=owner],th[data-sort=owner]{width:150px;max-width:150px}[data-col=city],th[data-sort=city]{width:86px;max-width:86px}[data-col=region],th[data-sort=region]{width:44px;max-width:44px}[data-col=stationClass],th[data-sort=stationClass]{width:70px;max-width:70px}[data-col=medium],th[data-sort=medium]{width:58px;max-width:58px}[data-col=type],th[data-sort=type]{width:66px;max-width:66px}[data-col=timeZone],th[data-sort=timeZone]{width:116px;max-width:116px}[data-col=provider],th[data-sort=provider]{width:90px;max-width:90px}
@media(max-width:900px){.app{grid-template-columns:1fr}aside{display:none}}
</style></head><body><div class="app"><aside>
<h1>M3U Review</h1><div class="stat"><span id="visibleCount">0</span> matching / __REVIEW_COUNT__ review</div>
<label>Find</label><input id="q" placeholder="Partial find: CTV, BET, HBO">
<label>Country</label><select id="country" multiple>__COUNTRY_OPTIONS__</select><div class="hint">Ctrl/Shift-click for multiple. None selected = all.</div>
<label>Category</label><select id="category" multiple>__CATEGORY_OPTIONS__</select>
<label>Decision</label><select id="decision" multiple>__DECISION_OPTIONS__<option value="keep">keep (manual)</option></select>
<label>Station Class</label><select id="stationClass" multiple></select>
<label>Group Rows By</label><select id="groupBy"><option value="">None</option><option value="country">Country</option><option value="category">Category</option><option value="station_class">Station Class</option><option value="network">Network</option><option value="owner">Owner</option><option value="provider">Provider</option></select>
<label>Bulk Filtered</label><div class="side-row"><button id="keepFiltered">Keep</button><button id="excludeFiltered">Exclude</button></div>
<label>Bulk Selected</label><div class="side-row"><button id="keepSelected">Keep</button><button id="excludeSelected">Exclude</button></div>
<label>Selection</label><div class="side-row"><button id="selectFiltered">Select All</button><button id="reverseFiltered">Reverse</button></div><button id="selectNone">Clear Selection</button>
<label>QA</label><button id="qaMixed">Show Mixed Name Status</button>
<label>Page Functions</label><button id="saveNow">Save so far</button><button id="export">Export JSON</button><button id="refresh">Refresh</button><button id="clear">Clear Edits</button>
<div id="status">Auto-save is on.</div>
</aside><main><div class="topbar"><button id="prevPage">Prev</button><span id="pageInfo"></span><button id="nextPage">Next</button><label>Rows</label><select id="pageSize"><option>100</option><option selected>250</option><option>500</option><option>1000</option></select></div><div class="table"><table id="tbl"><thead><tr>
<th data-sort="decision"><div class="head">Decision <span></span></div><select data-filter="decision"><option value="">All</option><option>review</option><option>keep</option><option>exclude</option></select></th>
<th><div class="head">Sel</div></th>
<th data-sort="name"><div class="head">Name <span></span></div><input data-filter="name" placeholder="filter"></th>
<th data-sort="call"><div class="head">Call <span></span></div><input data-filter="call"></th>
<th data-sort="country"><div class="head">Country <span></span></div><input data-filter="country"></th>
<th data-sort="category"><div class="head">Category <span></span></div><input data-filter="category"></th>
<th data-sort="network"><div class="head">Network <span></span></div><input data-filter="network"></th>
<th data-sort="owner"><div class="head">Owner <span></span></div><input data-filter="owner"></th>
<th data-sort="city"><div class="head">City <span></span></div><input data-filter="city"></th>
<th data-sort="region"><div class="head">Region <span></span></div><input data-filter="region"></th>
<th data-sort="stationClass"><div class="head">Class <span></span></div><input data-filter="stationClass"></th>
<th data-sort="medium"><div class="head">Med <span></span></div><input data-filter="medium"></th>
<th data-sort="type"><div class="head">Type <span></span></div><input data-filter="type"></th>
<th data-sort="timezone"><div class="head">Time Zone <span></span></div><input data-filter="timezone"></th>
<th data-sort="provider"><div class="head">Provider <span></span></div><input data-filter="provider"></th>
<th><div class="head">Notes</div></th>
</tr></thead><tbody id="body"></tbody></table></div></main></div><script>
const DATA=__DATA__;const INITIAL_STATE=__INITIAL_STATE__;const KEY='iptv_m3u_candidate_review_v1';const state={...INITIAL_STATE,...JSON.parse(localStorage.getItem(KEY)||'{}')};let filtered=[],page=1,sortKey='',sortDir=1,qaOnly=false,qaNames=new Set();
function save(){localStorage.setItem(KEY,JSON.stringify(state));status('Saved '+new Date().toLocaleTimeString());}
function status(msg){document.getElementById('status').textContent=msg;}
function selectedValues(id){return [...document.getElementById(id).selectedOptions].map(x=>x.value).filter(Boolean);}
function inSelected(values,value){return values.length===0||values.includes(value);}
function recDecision(r){return (state[r.id]&&state[r.id].decision)||r.decision;}
function recSelected(r){return !!(state[r.id]&&state[r.id].selected);}
function recNote(r){return (state[r.id]&&state[r.id].note)||'';}
function recVal(r,key){if(key==='decision')return recDecision(r);if(key==='timezone')return r.timeZone||'';return (r[key]||'').toString();}
function filters(){const out={q:document.getElementById('q').value.toLowerCase(),country:selectedValues('country'),category:selectedValues('category'),decision:selectedValues('decision'),stationClass:selectedValues('stationClass'),cols:{}};document.querySelectorAll('[data-filter]').forEach(x=>out.cols[x.dataset.filter]=x.value.toLowerCase());return out;}
function applyFilters(){const f=filters();filtered=DATA.filter(r=>{let ok=(!qaOnly||qaNames.has(normName(r.name)))&&(!f.q||r.search.includes(f.q))&&inSelected(f.country,r.country)&&inSelected(f.category,r.category)&&inSelected(f.stationClass,r.stationClass)&&inSelected(f.decision,recDecision(r));Object.entries(f.cols).forEach(([k,v])=>{if(v&&ok)ok=recVal(r,k).toLowerCase().includes(v);});return ok;});if(sortKey)filtered.sort((a,b)=>recVal(a,sortKey).localeCompare(recVal(b,sortKey),undefined,{numeric:true})*sortDir);page=1;render();}
function rowHtml(r){const s=state[r.id]||{},d=recDecision(r),sel=recSelected(r)?' checked':'';return `<tr data-id="${r.id}" class="${sel?'selected':''}"><td data-col="decision"><span class="pill decision-label ${d}">${d}</span><button class="mini keep" title="Keep">K</button><button class="mini exclude" title="Exclude">X</button><button class="mini review" title="Review">R</button></td><td data-col="select"><input class="sel" type="checkbox"${sel}></td><td class="name" data-col="name" title="${escHtml(r.name)}">${escHtml(r.name)}</td><td data-col="call">${escHtml(r.call)}</td><td data-col="country">${escHtml(r.country)}</td><td data-col="category">${escHtml(r.category)}</td><td data-col="network" title="${escHtml(r.network)}">${escHtml(r.network)}</td><td data-col="owner" title="${escHtml(r.owner)}">${escHtml(r.owner)}</td><td data-col="city">${escHtml(r.city)}</td><td data-col="region">${escHtml(r.region)}</td><td data-col="stationClass">${escHtml(r.stationClass)}</td><td data-col="medium">${escHtml(r.medium)}</td><td data-col="type">${escHtml(r.type)}</td><td data-col="timeZone">${escHtml(r.timeZone)}</td><td data-col="provider">${escHtml(r.provider)}</td><td data-col="notes"><input class="note" value="${escHtml(recNote(r))}" placeholder="note"></td></tr>`;}
function escHtml(v){return (v||'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function render(){const size=parseInt(document.getElementById('pageSize').value,10),pages=Math.max(1,Math.ceil(filtered.length/size));if(page>pages)page=pages;const start=(page-1)*size,slice=filtered.slice(start,start+size);document.getElementById('body').innerHTML=slice.map(rowHtml).join('');document.getElementById('visibleCount').textContent=filtered.length;document.getElementById('pageInfo').textContent=`Page ${page}/${pages} rows ${start+1}-${Math.min(start+size,filtered.length)}`;}
function updateDecision(ids,d){ids.forEach(id=>{state[id]=state[id]||{};state[id].decision=d;});save();applyFilters();}
function updateSelected(ids,selected){ids.forEach(id=>{state[id]=state[id]||{};state[id].selected=selected;});save();render();}
function selectedIds(){return DATA.filter(r=>recSelected(r)).map(r=>r.id);}
function sortBy(key){sortDir=sortKey===key?-sortDir:1;sortKey=key;applyFilters();}
function normName(name){return (name||'').toLowerCase().replace(/\[[^\]]*\]|\([^)]*\)/g,' ').replace(/\b(4k|uhd|fhd|hd|sd|720p|1080p|540p|480p)\b/g,' ').replace(/[^a-z0-9]+/g,' ').trim();}
function toggleQaMixed(){if(qaOnly){qaOnly=false;qaNames.clear();document.getElementById('qaMixed').textContent='Show Mixed Name Status';applyFilters();return;}const map=new Map();DATA.forEach(r=>{const n=normName(r.name);if(!n)return;if(!map.has(n))map.set(n,new Set());map.get(n).add(recDecision(r));});qaNames=new Set([...map.entries()].filter(([n,s])=>s.size>1).map(([n])=>n));qaOnly=true;document.getElementById('qaMixed').textContent='Clear Mixed QA';applyFilters();status(`${qaNames.size} names have mixed keep/review/exclude statuses.`);}
function exportDecisions(){const decisions=DATA.map(x=>{const s=state[x.id]||{};return {...x,manualDecision:s.decision||x.decision,selected:!!s.selected,note:s.note||''};});const b=new Blob([JSON.stringify({exportedAt:new Date().toISOString(),decisions},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='m3u_candidate_review_decisions.json';a.click();URL.revokeObjectURL(a.href);}
const classes=[...new Set(DATA.map(r=>r.stationClass).filter(Boolean))].sort();document.getElementById('stationClass').innerHTML=classes.map(x=>`<option>${x}</option>`).join('');
document.getElementById('body').onclick=e=>{const row=e.target.closest('tr');if(!row)return;const id=row.dataset.id;if(e.target.closest('button')){if(e.target.classList.contains('keep'))updateDecision([id],'keep');if(e.target.classList.contains('exclude'))updateDecision([id],'exclude');if(e.target.classList.contains('review'))updateDecision([id],'review');return;}if(e.target.classList.contains('note'))return;const r=DATA.find(x=>x.id===id);state[id]=state[id]||{};state[id].selected=!recSelected(r);save();render();};
document.getElementById('body').oninput=e=>{if(!e.target.classList.contains('note'))return;const id=e.target.closest('tr').dataset.id;state[id]=state[id]||{};state[id].note=e.target.value;save();};
['q','country','category','decision','stationClass','pageSize'].forEach(id=>document.getElementById(id).oninput=applyFilters);document.getElementById('groupBy').oninput=e=>{if(e.target.value)sortBy(e.target.value);};document.querySelectorAll('[data-filter]').forEach(x=>x.oninput=applyFilters);document.querySelectorAll('th[data-sort] .head').forEach(h=>h.onclick=()=>sortBy(h.parentElement.dataset.sort));
document.getElementById('prevPage').onclick=()=>{page=Math.max(1,page-1);render();};document.getElementById('nextPage').onclick=()=>{page++;render();};document.getElementById('keepFiltered').onclick=()=>updateDecision(filtered.map(r=>r.id),'keep');document.getElementById('excludeFiltered').onclick=()=>updateDecision(filtered.map(r=>r.id),'exclude');document.getElementById('keepSelected').onclick=()=>updateDecision(selectedIds(),'keep');document.getElementById('excludeSelected').onclick=()=>updateDecision(selectedIds(),'exclude');document.getElementById('selectFiltered').onclick=()=>updateSelected(filtered.map(r=>r.id),true);document.getElementById('reverseFiltered').onclick=()=>{filtered.forEach(r=>{state[r.id]=state[r.id]||{};state[r.id].selected=!recSelected(r);});save();render();};document.getElementById('selectNone').onclick=()=>{Object.values(state).forEach(s=>s.selected=false);save();render();};document.getElementById('qaMixed').onclick=toggleQaMixed;document.getElementById('saveNow').onclick=save;document.getElementById('export').onclick=exportDecisions;document.getElementById('refresh').onclick=()=>location.reload();document.getElementById('clear').onclick=()=>{if(confirm('Clear saved local review edits?')){localStorage.removeItem(KEY);location.reload();}};applyFilters();
</script></body></html>"""
    return (
        template
        .replace("__DATA__", embedded)
        .replace("__INITIAL_STATE__", json.dumps(initial_state or {}, ensure_ascii=True))
        .replace("__REVIEW_COUNT__", str(len(review_records)))
        .replace("__COUNTRY_OPTIONS__", options(report["summary"]["country_counts"]))
        .replace("__CATEGORY_OPTIONS__", options(report["summary"]["category_counts"]))
        .replace("__DECISION_OPTIONS__", options(report["summary"]["decision_counts"]))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build M3U scope candidate review report.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--m3u-dir", type=Path, action="append", default=None)
    parser.add_argument("--matrix", type=Path, default=MATRIX_DEFAULT)
    parser.add_argument("--prior-decisions", type=Path, default=Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid\ouput\m3u_candidate_review_decisions.json"))
    args = parser.parse_args()

    policy = load_json(args.repo / "config" / "scope_policy.active.json")
    matrix = load_matrix(args.matrix)
    m3u_dirs = args.m3u_dir or DEFAULT_M3U_DIRS
    m3u_files = discover_m3u_files(m3u_dirs)
    prior = load_prior_decisions(args.prior_decisions)
    records_by_key: dict[str, dict] = {}
    seen_urls = Counter()
    source_file_counts = []

    for path in m3u_files:
        parsed = parse_m3u(path)
        source_file_counts.append({"file": str(path), "records": len(parsed)})
        for record in parsed:
            key = record["source_stream_url"] or "|".join([record["source_file"], record["source_record_name"], record["source_tvg_id"]])
            if key in records_by_key:
                records_by_key[key] = merge_duplicate_record(records_by_key[key], record)
            else:
                records_by_key[key] = record
            if record["source_stream_url"]:
                seen_urls[record["source_stream_url"]] += 1

    records = []
    initial_state = {}
    for record in records_by_key.values():
        classification = classify(record, policy)
        metadata = enrich(record, classification, matrix)
        merged = {"review_id": stable_review_id(record), **record, **classification, **metadata}
        merged["canonical_seed"] = canonical_seed(record, classification, metadata, policy["alternate_label_policy"]["style"])
        prior_state = prior_state_for_record(record, prior)
        if prior_state:
            initial_state[merged["review_id"]] = prior_state
        records.append(merged)

    records.sort(key=lambda item: (item["country"], item["category"], item["network"], item["source_record_name"]))

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "total_records": len(records),
            "raw_records_scanned": sum(item["records"] for item in source_file_counts),
            "m3u_file_count": len(m3u_files),
            "unique_stream_url_count": len(seen_urls),
            "duplicate_stream_url_count": sum(count - 1 for count in seen_urls.values() if count > 1),
            "decision_counts": dict(Counter(item["decision"] for item in records)),
            "country_counts": dict(Counter(item["country"] for item in records)),
            "category_counts": dict(Counter(item["category"] for item in records)),
            "station_class_counts": dict(Counter(item["station_class"] for item in records)),
            "top_network_counts": dict(Counter(item["network"] or "UNKNOWN" for item in records).most_common(50)),
            "metadata_confidence_counts": dict(Counter(item["metadata_confidence"] for item in records)),
            "prior_decisions_imported": len(initial_state),
        },
        "source_file_counts": source_file_counts,
        "sample_candidates": records[:1000],
    }

    (args.repo / "reports").mkdir(exist_ok=True)
    (args.repo / "data").mkdir(exist_ok=True)
    (args.repo / "reports" / "m3u_scope_candidates.html").write_text(render_html(report, records, initial_state), encoding="utf-8")
    (args.repo / "reports" / "m3u_scope_candidates.summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.repo / "data" / "m3u_scope_candidates.records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Records: {len(records)}")
    print(f"Raw records scanned: {report['summary']['raw_records_scanned']}")
    print(f"M3U files: {len(m3u_files)}")
    print(f"Prior decisions imported: {len(initial_state)}")
    print(f"Decisions: {report['summary']['decision_counts']}")
    print(f"Countries: {report['summary']['country_counts']}")
    print(f"Categories: {report['summary']['category_counts']}")
    print(f"Metadata confidence: {report['summary']['metadata_confidence_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
