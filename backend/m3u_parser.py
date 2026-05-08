# m3u_parser.py

import re
from typing import List, Dict, Tuple


EXTINF_PREFIX = "#EXTINF"


def parse_m3u_text(text: str) -> List[Dict]:
    """
    Parse raw M3U content into a list of channel dicts.

    Each dict:
      {
        "name": str,
        "url": str,
        "tvg_id": str | None,
        "tvg_name": str | None,
        "tvg_logo": str | None,
        "group_title": str | None,
        "raw_extinf": str,
      }
    """
    lines = [line.strip() for line in text.splitlines() if line.strip() != ""]
    channels = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith(EXTINF_PREFIX):
            extinf_line = line
            url_line = None

            if i + 1 < len(lines):
                candidate = lines[i + 1]
                if not candidate.startswith("#"):
                    url_line = candidate

            channel = _parse_extinf_and_url(extinf_line, url_line)
            if channel:
                channels.append(channel)
            i += 2
        else:
            i += 1

    return channels


def _parse_extinf_and_url(extinf_line: str, url_line: str) -> Dict:
    # Example formats:
    # #EXTINF:-1 tvg-id="xxx" tvg-name="xxx" tvg-logo="xxx" group-title="News",Channel Name
    # #EXTINF:-1, US HBO SIGNATURE (East) Backup NO_4 alliptvlinks.com

    attrs_part, name_part = _split_extinf_line(extinf_line)

    attrs = _parse_extinf_attributes(attrs_part)

    name = name_part.strip() if name_part else "Unknown"
    tvg_id = attrs.get("tvg-id")
    tvg_name = attrs.get("tvg-name")
    tvg_logo = attrs.get("tvg-logo")
    group_title = attrs.get("group-title")

    # Fallbacks
    if not tvg_name:
        tvg_name = name

    # Basic cleanup: strip common junk suffixes
    name = _clean_channel_name(name)

    return {
        "name": name,
        "url": url_line or "",
        "tvg_id": tvg_id,
        "tvg_name": tvg_name,
        "tvg_logo": tvg_logo,
        "group_title": group_title,
        "raw_extinf": extinf_line,
    }


def _split_extinf_line(extinf_line: str) -> Tuple[str, str]:
    # Remove prefix
    if ":" in extinf_line:
        _, rest = extinf_line.split(":", 1)
    else:
        rest = extinf_line

    # Split on first comma to separate attributes from name
    if "," in rest:
        attrs_part, name_part = rest.split(",", 1)
    else:
        attrs_part, name_part = rest, ""

    return attrs_part.strip(), name_part.strip()


def _parse_extinf_attributes(attrs_part: str) -> Dict[str, str]:
    # Regex to match key="value" pairs
    pattern = re.compile(r'(\w+(?:-\w+)*)="([^"]*)"')
    attrs = dict(pattern.findall(attrs_part))
    return attrs


def _clean_channel_name(name: str) -> str:
    # Remove common junk tokens
    junk_patterns = [
        r"\s*alliptvlinks\.com\s*",
        r"\s*backup\s*no?[_\s]*\d+\s*",
        r"\s*checkedby:[^ ]+\s*",
    ]

    cleaned = name
    for pat in junk_patterns:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else name


def merge_playlists(playlists: List[List[Dict]]) -> List[Dict]:
    """
    Merge multiple channel lists and dedupe.
    Dedupe key: (normalized_name, url) primarily, fallback to url.
    """
    merged: Dict[Tuple[str, str], Dict] = {}

    for channels in playlists:
        for ch in channels:
            name_key = ch.get("name", "").strip().lower()
            url_key = ch.get("url", "").strip()
            key = (name_key, url_key or name_key)

            if key not in merged:
                merged[key] = ch
            else:
                existing = merged[key]
                merged[key] = _prefer_richer_metadata(existing, ch)

    return list(merged.values())


def _prefer_richer_metadata(a: Dict, b: Dict) -> Dict:
    """
    Choose the channel dict with more useful metadata.
    """
    def richness(ch: Dict) -> int:
        score = 0
        for field in ["tvg_logo", "tvg_id", "group_title"]:
            if ch.get(field):
                score += 1
        return score

    return a if richness(a) >= richness(b) else b


def export_to_m3u(channels: List[Dict]) -> str:
    """
    Export list of channel dicts to M3U string.
    """
    lines = ["#EXTM3U"]

    for ch in channels:
        parts = ["#EXTINF:-1"]
        if ch.get("tvg_id"):
            parts.append(f'tvg-id="{ch["tvg_id"]}"')
        if ch.get("tvg_name"):
            parts.append(f'tvg-name="{ch["tvg_name"]}"')
        if ch.get("tvg_logo"):
            parts.append(f'tvg-logo="{ch["tvg_logo"]}"')
        if ch.get("group_title"):
            parts.append(f'group-title="{ch["group_title"]}"')

        name = ch.get("name") or ch.get("tvg_name") or "Unknown"
        extinf_line = " ".join(parts) + f",{name}"

        lines.append(extinf_line)
        lines.append(ch.get("url", ""))

    return "\n".join(lines) + "\n"
