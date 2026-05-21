from __future__ import annotations

import csv
import hashlib
import html
import json
import logging
import os
import re
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CSV_ENCODING = "utf-8-sig"
CHUNK_SIZE_BYTES = 1024 * 256
HTTP_TIMEOUT_SECONDS = 120
VALID_SOURCE_TYPES = {"direct_urls", "xtream_codes"}
ITEM_TYPES = {"live_tv", "vod_movie", "series", "series_episode", "catchup", "unknown"}

XTREAM_FETCH_TARGETS = {
    "player_api_live_categories.json": "get_live_categories",
    "player_api_live_streams.json": "get_live_streams",
    "player_api_vod_categories.json": "get_vod_categories",
    "player_api_vod_streams.json": "get_vod_streams",
    "player_api_series_categories.json": "get_series_categories",
    "player_api_series.json": "get_series",
}

PROFILE_FIELDS = [
    "source_key",
    "source_display_name",
    "source_type",
    "provider_label",
    "created_at",
    "last_fetch_at",
    "last_parse_at",
    "server_host",
    "m3u_url_redacted",
    "epg_url_redacted",
    "has_credentials_local",
    "source_status",
    "notes",
]

ALL_STREAM_FIELDS = [
    "source_key",
    "source_display_name",
    "source_type",
    "dataset_timestamp",
    "record_key",
    "source_record_number",
    "extinf_line_number",
    "stream_url_line_number",
    "raw_extinf",
    "raw_title",
    "normalized_title",
    "item_type",
    "item_type_reason",
    "tvg_id",
    "tvg_name",
    "tvg_logo",
    "group_title",
    "group_path",
    "group_region_token",
    "group_language_token",
    "group_content_token",
    "stream_url_private",
    "stream_url_redacted",
    "stream_scheme",
    "stream_host",
    "stream_path",
    "stream_extension",
    "stream_id_candidate",
    "xtream_category_id",
    "xtream_category_name",
    "xtream_stream_id",
    "xtream_series_id",
    "xtream_episode_id",
    "epg_channel_id_match",
    "epg_display_name_match",
    "epg_match_method",
    "epg_match_confidence",
    "network_raw",
    "network_normalized",
    "network_country",
    "network_match_method",
    "network_match_confidence",
    "country_raw",
    "country_normalized",
    "country_derivation_method",
    "language_raw",
    "language_normalized",
    "language_derivation_method",
    "location_raw",
    "location_normalized",
    "feed_variant",
    "is_hd",
    "is_fhd",
    "is_uhd",
    "is_4k",
    "is_sd",
    "is_backup",
    "is_hevc",
    "is_catchup",
    "is_adult",
    "is_sports",
    "include_candidate",
    "exclude_candidate",
    "notes",
]

EPG_CHANNEL_FIELDS = [
    "source_key",
    "dataset_timestamp",
    "epg_channel_id",
    "display_name_primary",
    "display_names_all",
    "icon_src",
    "url",
    "matched_m3u_record_key",
    "matched_m3u_title",
    "match_method",
    "match_confidence",
]

EPG_PROGRAMME_FIELDS = [
    "source_key",
    "dataset_timestamp",
    "programme_key",
    "channel_id",
    "matched_m3u_record_key",
    "start_raw",
    "stop_raw",
    "start_local",
    "stop_local",
    "duration_minutes",
    "title",
    "sub_title",
    "desc",
    "category_all",
    "episode_num_all",
    "episode_num_xmltv_ns",
    "episode_num_onscreen",
    "date",
    "country",
    "language",
    "credits_director",
    "credits_actor",
    "rating_system",
    "rating_value",
    "icon_src",
    "previously_shown",
    "premiere",
    "new",
    "live",
    "audio",
    "subtitles",
]

FETCH_MANIFEST_FIELDS = [
    "source_key",
    "dataset_timestamp",
    "file_label",
    "url_redacted",
    "latest_path",
    "snapshot_path",
    "bytes",
    "sha256",
    "status",
    "error",
]

PARSE_MANIFEST_FIELDS = [
    "source_key",
    "dataset_timestamp",
    "artifact",
    "path",
    "rows",
    "status",
    "notes",
]

GROUP_SUMMARY_FIELDS = ["source_key", "dataset_timestamp", "group_title", "item_type", "record_count"]
NETWORK_AUDIT_FIELDS = [
    "source_key",
    "dataset_timestamp",
    "record_key",
    "candidate_text",
    "network_normalized",
    "network_country",
    "match_method",
    "match_confidence",
]
COUNTRY_LANGUAGE_AUDIT_FIELDS = [
    "source_key",
    "dataset_timestamp",
    "record_key",
    "country_raw",
    "country_normalized",
    "country_derivation_method",
    "country_confidence",
    "language_raw",
    "language_normalized",
    "language_derivation_method",
    "language_confidence",
]
SCOPE_RULE_FIELDS = ["action", "field_name", "operator", "value", "case_sensitive", "enabled", "notes"]
SCOPE_CANDIDATE_FIELDS = ALL_STREAM_FIELDS + ["scope_action", "scope_reason"]


@dataclass(frozen=True)
class SourcePaths:
    source_key: str
    latest_raw: Path
    snapshot_raw: Path
    latest_report: Path
    snapshot_report: Path
    scope_dir: Path
    web_feed_dir: Path


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parent.parent


def clean_source_key(value: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip()).strip("_").lower()
    if not key:
        raise ValueError("source_key is required")
    return key


def normalize_space(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_token(value: Any) -> str:
    text = normalize_space(value).lower()
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_space(text)


def redact_value(value: str, keep_start: int = 3, keep_end: int = 2) -> str:
    if not value:
        return ""
    if len(value) <= keep_start + keep_end:
        return "***"
    return f"{value[:keep_start]}***{value[-keep_end:]}"


def redact_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        sensitive = {"username", "user", "password", "pass", "token", "key", "api_key"}
        query = []
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            query.append((key, redact_value(value) if key.lower() in sensitive else value))
        netloc = parsed.netloc
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{redact_value(parsed.username or '')}:***@{host}{port}"
        return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))
    except Exception:
        return "[unparseable_url_redacted]"


def server_host(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        return parsed.hostname or ""
    except Exception:
        return ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_SIZE_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def profile_public_path(repo_root: Path) -> Path:
    return repo_root / "data" / "source_profiles" / "source_profiles_public.json"


def profile_private_path(repo_root: Path) -> Path:
    return repo_root / "data" / "source_profiles" / "source_profiles.private.json"


def source_paths(repo_root: Path, source_key: str, stamp: str | None = None) -> SourcePaths:
    key = clean_source_key(source_key)
    dataset_stamp = stamp or utc_stamp()
    return SourcePaths(
        source_key=key,
        latest_raw=repo_root / "data" / "provider_feeds" / key / "raw" / "latest",
        snapshot_raw=repo_root / "data" / "provider_feeds" / key / "raw" / "snapshots" / dataset_stamp,
        latest_report=repo_root / "reports" / "provider_inventory" / key / "latest",
        snapshot_report=repo_root / "reports" / "provider_inventory" / key / "snapshots" / dataset_stamp,
        scope_dir=repo_root / "data" / "channel_scope" / key,
        web_feed_dir=repo_root / "web" / "feeds" / key,
    )


def ensure_base_files(repo_root: Path) -> None:
    public_path = profile_public_path(repo_root)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    if not public_path.exists():
        public_path.write_text(json.dumps({"version": 1, "profiles": []}, indent=2), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_public_profiles(repo_root: Path) -> dict[str, dict[str, Any]]:
    ensure_base_files(repo_root)
    payload = load_json(profile_public_path(repo_root), {"version": 1, "profiles": []})
    return {clean_source_key(item.get("source_key", "")): dict(item) for item in payload.get("profiles", []) if item.get("source_key")}


def load_private_profiles(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(profile_private_path(repo_root), {"version": 1, "profiles": {}})
    profiles = payload.get("profiles", {})
    if isinstance(profiles, list):
        return {clean_source_key(item.get("source_key", "")): dict(item) for item in profiles if item.get("source_key")}
    return {clean_source_key(key): dict(value) for key, value in profiles.items()}


def save_public_profiles(repo_root: Path, profiles: dict[str, dict[str, Any]]) -> None:
    ordered = [profiles[key] for key in sorted(profiles)]
    write_json(profile_public_path(repo_root), {"version": 1, "profiles": ordered})


def save_private_profiles(repo_root: Path, profiles: dict[str, dict[str, Any]]) -> None:
    write_json(profile_private_path(repo_root), {"version": 1, "profiles": {key: profiles[key] for key in sorted(profiles)}})


def derive_xtream_urls(server_url: str, username: str, password: str) -> dict[str, str]:
    server = (server_url or "").strip().rstrip("/")
    query = urllib.parse.urlencode({"username": username, "password": password})
    return {
        "m3u_url": f"{server}/get.php?{query}&type=m3u_plus&output=hls",
        "epg_url": f"{server}/xmltv.php?{query}",
        "api_base": f"{server}/player_api.php?{query}",
    }


def resolve_source_urls(repo_root: Path, source_key: str) -> dict[str, str]:
    key = clean_source_key(source_key)
    public = load_public_profiles(repo_root).get(key, {})
    private = load_private_profiles(repo_root).get(key, {})
    source_type = public.get("source_type") or private.get("source_type") or "direct_urls"
    if source_type == "xtream_codes":
        urls = derive_xtream_urls(private.get("server_url", ""), private.get("username", ""), private.get("password", ""))
    else:
        urls = {
            "m3u_url": private.get("m3u_url", ""),
            "epg_url": private.get("epg_url", ""),
            "api_base": "",
        }
    return {key_name: normalize_space(value) for key_name, value in urls.items()}


def upsert_source_profile(repo_root: Path, public_data: dict[str, Any], private_data: dict[str, Any] | None = None) -> dict[str, Any]:
    profiles = load_public_profiles(repo_root)
    private_profiles = load_private_profiles(repo_root)
    key = clean_source_key(public_data.get("source_key", ""))
    source_type = public_data.get("source_type") or private_data.get("source_type") if private_data else public_data.get("source_type")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")
    existing = profiles.get(key, {})
    created_at = existing.get("created_at") or utc_iso()
    private_record = dict(private_profiles.get(key, {}))
    if private_data:
        private_record.update({name: value for name, value in private_data.items() if value is not None})
        private_record["source_type"] = source_type
        private_profiles[key] = private_record
    urls = derive_xtream_urls(private_record.get("server_url", ""), private_record.get("username", ""), private_record.get("password", "")) if source_type == "xtream_codes" else {
        "m3u_url": private_record.get("m3u_url", ""),
        "epg_url": private_record.get("epg_url", ""),
    }
    public_record = {
        "source_key": key,
        "source_display_name": normalize_space(public_data.get("source_display_name") or existing.get("source_display_name") or key),
        "source_type": source_type,
        "provider_label": normalize_space(public_data.get("provider_label") or existing.get("provider_label") or ""),
        "created_at": created_at,
        "last_fetch_at": existing.get("last_fetch_at", ""),
        "last_parse_at": existing.get("last_parse_at", ""),
        "server_host": server_host(private_record.get("server_url") or urls.get("m3u_url", "")),
        "m3u_url_redacted": redact_url(urls.get("m3u_url", "")),
        "epg_url_redacted": redact_url(urls.get("epg_url", "")),
        "has_credentials_local": bool(private_record),
        "source_status": normalize_space(public_data.get("source_status") or existing.get("source_status") or "configured"),
        "notes": normalize_space(public_data.get("notes") or existing.get("notes") or ""),
    }
    profiles[key] = public_record
    save_public_profiles(repo_root, profiles)
    if private_data:
        save_private_profiles(repo_root, private_profiles)
    return public_record


def update_profile_status(repo_root: Path, source_key: str, **updates: Any) -> None:
    profiles = load_public_profiles(repo_root)
    key = clean_source_key(source_key)
    if key not in profiles:
        return
    profiles[key].update({name: value for name, value in updates.items() if name in PROFILE_FIELDS})
    save_public_profiles(repo_root, profiles)


def archive_source_profile(repo_root: Path, source_key: str) -> dict[str, Any]:
    profiles = load_public_profiles(repo_root)
    key = clean_source_key(source_key)
    if key not in profiles:
        raise ValueError(f"Unknown source profile: {key}")
    profiles[key]["source_status"] = "archived"
    profiles[key]["notes"] = normalize_space(f"{profiles[key].get('notes', '')} Archived at {utc_iso()}.")
    save_public_profiles(repo_root, profiles)
    return profiles[key]


def delete_source_profile(repo_root: Path, source_key: str, delete_private: bool = True) -> dict[str, Any]:
    profiles = load_public_profiles(repo_root)
    private_profiles = load_private_profiles(repo_root)
    key = clean_source_key(source_key)
    removed_public = profiles.pop(key, None)
    removed_private = private_profiles.pop(key, None) if delete_private else None
    if removed_public is None and removed_private is None:
        raise ValueError(f"Unknown source profile: {key}")
    save_public_profiles(repo_root, profiles)
    if delete_private:
        save_private_profiles(repo_root, private_profiles)
    return {
        "source_key": key,
        "removed_public_profile": bool(removed_public),
        "removed_private_profile": bool(removed_private),
        "datasets_preserved": True,
    }


def configure_logger(repo_root: Path, name: str, file_name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / file_name, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger


def fetch_url(url: str, latest_path: Path, snapshot_path: Path, logger: logging.Logger, source_key: str, label: str) -> dict[str, Any]:
    if not url:
        return {"source_key": source_key, "file_label": label, "status": "skipped", "error": "url_not_configured"}
    started = utc_iso()
    logger.info("fetch_start source_key=%s label=%s url=%s latest=%s snapshot=%s", source_key, label, redact_url(url), latest_path, snapshot_path)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "IPTV_Manager_Hybrid/multi-source", "Accept": "*/*"})
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            with snapshot_path.open("wb") as handle:
                while True:
                    chunk = response.read(CHUNK_SIZE_BYTES)
                    if not chunk:
                        break
                    handle.write(chunk)
        shutil.copy2(snapshot_path, latest_path)
        digest = sha256_file(latest_path)
        logger.info(
            "fetch_complete source_key=%s label=%s start=%s end=%s bytes=%s sha256=%s",
            source_key,
            label,
            started,
            utc_iso(),
            latest_path.stat().st_size,
            digest,
        )
        return {
            "source_key": source_key,
            "file_label": label,
            "url_redacted": redact_url(url),
            "latest_path": str(latest_path),
            "snapshot_path": str(snapshot_path),
            "bytes": str(latest_path.stat().st_size),
            "sha256": digest,
            "status": "ok",
            "error": "",
        }
    except Exception as exc:
        logger.error("fetch_error source_key=%s label=%s error=%s", source_key, label, exc)
        return {
            "source_key": source_key,
            "file_label": label,
            "url_redacted": redact_url(url),
            "latest_path": str(latest_path),
            "snapshot_path": str(snapshot_path),
            "bytes": "0",
            "sha256": "",
            "status": "error",
            "error": str(exc),
        }


def fetch_source(repo_root: Path, source_key: str, fetch_m3u: bool = True, fetch_epg: bool = True, fetch_xtream: bool = True) -> dict[str, Any]:
    key = clean_source_key(source_key)
    stamp = utc_stamp()
    paths = source_paths(repo_root, key, stamp)
    logger = configure_logger(repo_root, "source_fetch", "source_fetch.log.txt")
    profiles = load_public_profiles(repo_root)
    profile = profiles.get(key)
    if not profile:
        raise ValueError(f"Unknown source profile: {key}")
    urls = resolve_source_urls(repo_root, key)
    rows: list[dict[str, Any]] = []
    if fetch_m3u:
        rows.append(fetch_url(urls.get("m3u_url", ""), paths.latest_raw / "playlist.m3u", paths.snapshot_raw / "playlist.m3u", logger, key, "playlist.m3u"))
    if fetch_epg:
        rows.append(fetch_url(urls.get("epg_url", ""), paths.latest_raw / "epg.xml", paths.snapshot_raw / "epg.xml", logger, key, "epg.xml"))
    if fetch_xtream and profile.get("source_type") == "xtream_codes" and urls.get("api_base"):
        separator = "&" if "?" in urls["api_base"] else "?"
        for file_name, action in XTREAM_FETCH_TARGETS.items():
            rows.append(fetch_url(f"{urls['api_base']}{separator}action={action}", paths.latest_raw / file_name, paths.snapshot_raw / file_name, logger, key, file_name))
    manifest_rows = []
    for row in rows:
        item = {field: "" for field in FETCH_MANIFEST_FIELDS}
        item.update(row)
        item["dataset_timestamp"] = stamp
        manifest_rows.append(item)
    write_tsv(paths.latest_report / "source_fetch_manifest.tsv", manifest_rows, FETCH_MANIFEST_FIELDS)
    write_tsv(paths.snapshot_report / "source_fetch_manifest.tsv", manifest_rows, FETCH_MANIFEST_FIELDS)
    failed = [row for row in manifest_rows if row.get("status") == "error"]
    skipped = [row for row in manifest_rows if row.get("status") == "skipped"]
    ok_rows = [row for row in manifest_rows if row.get("status") == "ok"]
    if failed:
        source_status = "fetch_error" if not ok_rows else "partial_fetch"
    elif skipped:
        source_status = "partial_fetch"
    else:
        source_status = "fetched"
    update_profile_status(repo_root, key, last_fetch_at=utc_iso(), source_status=source_status)
    return {
        "source_key": key,
        "dataset_timestamp": stamp,
        "manifest_rows": manifest_rows,
        "latest_report": str(paths.latest_report),
        "overall_status": source_status,
        "ok_files": len(ok_rows),
        "failed_files": len(failed),
        "skipped_files": len(skipped),
    }


def detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[:65536]
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def split_first_unquoted_comma(value: str) -> tuple[str, str]:
    quote = ""
    for index, char in enumerate(value):
        if char in {"'", '"'}:
            quote = "" if quote == char else char if not quote else quote
        elif char == "," and not quote:
            return value[:index], value[index + 1 :]
    return value, ""


def parse_attributes(value: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    pattern = re.compile(r"(?P<key>[A-Za-z0-9_.:-]+)\s*=\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s,]+)")
    for match in pattern.finditer(value or ""):
        raw = match.group("value").strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        attrs[match.group("key").lower()] = html.unescape(raw.strip())
    return attrs


def parse_extinf(line: str) -> dict[str, Any]:
    body = line[len("#EXTINF:") :].strip() if line.upper().startswith("#EXTINF:") else line
    before, title = split_first_unquoted_comma(body)
    duration_match = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*(.*)$", before.strip())
    attr_text = duration_match.group(2).strip() if duration_match else before.strip()
    return {"raw_extinf": line, "raw_title": html.unescape(title.strip()), "attributes": parse_attributes(attr_text)}


def parse_stream_url(value: str) -> dict[str, str]:
    try:
        parsed = urllib.parse.urlsplit((value or "").strip())
        path = parsed.path or ""
        extension = Path(path).suffix.lower().lstrip(".")
        stream_id = ""
        match = re.search(r"/(?:live|movie|series)/[^/]+/[^/]+/(\d+)(?:\.|$)", path)
        if not match:
            match = re.search(r"/(\d+)(?:\.[A-Za-z0-9]+)?$", path)
        if match:
            stream_id = match.group(1)
        return {
            "scheme": parsed.scheme,
            "host": parsed.hostname or "",
            "path": path,
            "extension": extension,
            "stream_id_candidate": stream_id,
            "redacted_url": redact_url(value),
        }
    except Exception:
        return {"scheme": "", "host": "", "path": "", "extension": "", "stream_id_candidate": "", "redacted_url": "[unparseable_url_redacted]"}


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def load_reference_networks(repo_root: Path) -> dict[str, dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    candidates = [repo_root / "data" / "channel_scope" / "focused_channels.csv", repo_root / "data" / "channel_scope" / "focused_channels.json"]
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix.lower() == ".csv":
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
            else:
                rows = load_json(path, [])
            for row in rows:
                network = normalize_space(row.get("network", ""))
                if not network:
                    continue
                country = normalize_space(row.get("country", "") or row.get("location", ""))
                aliases = {
                    network,
                    row.get("selected_channel_name", ""),
                    row.get("tvg_name", ""),
                    row.get("tvg_id", ""),
                }
                for alias in aliases:
                    key = normalize_token(alias)
                    if key:
                        refs.setdefault(key, {"network": network, "country": country, "method": f"repo_reference:{path.as_posix()}"})
        except Exception:
            continue
    return refs


def match_network(refs: dict[str, dict[str, str]], candidates: list[str]) -> dict[str, str]:
    for candidate in candidates:
        key = normalize_token(candidate)
        if key in refs:
            ref = refs[key]
            return {"raw": candidate, "normalized": ref["network"], "country": ref.get("country", ""), "method": ref["method"] + ":exact_alias", "confidence": "1.00"}
    for candidate in candidates:
        candidate_key = normalize_token(candidate)
        if not candidate_key:
            continue
        padded = f" {candidate_key} "
        for alias_key, ref in refs.items():
            if alias_key and f" {alias_key} " in padded:
                return {"raw": candidate, "normalized": ref["network"], "country": ref.get("country", ""), "method": ref["method"] + ":normalized_alias", "confidence": "0.85"}
    return {"raw": " | ".join(filter(None, candidates)), "normalized": "", "country": "", "method": "none", "confidence": "0"}


def deterministic_country(value: str) -> tuple[str, str, str, str]:
    text = normalize_token(value)
    tokens = {
        " ca ": ("CA", "explicit_token", "0.90"),
        " canada ": ("CA", "explicit_token", "0.90"),
        " us ": ("US", "explicit_token", "0.90"),
        " usa ": ("US", "explicit_token", "0.90"),
        " united states ": ("US", "explicit_token", "0.90"),
        " uk ": ("UK", "explicit_token", "0.90"),
        " united kingdom ": ("UK", "explicit_token", "0.90"),
        " au ": ("AU", "explicit_token", "0.90"),
        " australia ": ("AU", "explicit_token", "0.90"),
    }
    padded = f" {text} "
    for token, result in tokens.items():
        if token in padded:
            return value, result[0], result[1], result[2]
    return "", "", "none", "0"


def deterministic_language(value: str) -> tuple[str, str, str, str]:
    text = normalize_token(value)
    tokens = {
        " english ": ("English", "explicit_token", "0.90"),
        " en ": ("English", "explicit_token", "0.80"),
        " french ": ("French", "explicit_token", "0.90"),
        " francais ": ("French", "explicit_token", "0.90"),
        " fr ": ("French", "explicit_token", "0.80"),
        " spanish ": ("Spanish", "explicit_token", "0.90"),
        " espanol ": ("Spanish", "explicit_token", "0.90"),
        " es ": ("Spanish", "explicit_token", "0.80"),
    }
    padded = f" {text} "
    for token, result in tokens.items():
        if token in padded:
            return value, result[0], result[1], result[2]
    return "", "", "none", "0"


def derive_group_tokens(group_title: str) -> tuple[str, str, str]:
    parts = [normalize_space(part) for part in re.split(r"[|>/\\:-]+", group_title or "") if normalize_space(part)]
    region = ""
    language = ""
    content = ""
    for part in parts:
        _, country_value, country_method, _ = deterministic_country(part)
        _, language_value, language_method, _ = deterministic_language(part)
        if country_value and country_method != "none" and not region:
            region = part
        elif language_value and language_method != "none" and not language:
            language = part
        elif not content:
            content = part
    return region, language, content


def classify_item(row: dict[str, str], xtream_by_stream_id: dict[str, dict[str, str]]) -> tuple[str, str]:
    stream_id = row.get("stream_id_candidate", "")
    if stream_id and stream_id in xtream_by_stream_id:
        info = xtream_by_stream_id[stream_id]
        return info.get("item_type", "unknown"), "xtream_api_metadata"
    path = row.get("stream_path", "").lower()
    group = normalize_token(row.get("group_title", ""))
    title = normalize_token(row.get("raw_title", ""))
    if row.get("is_catchup") == "Y":
        return "catchup", "m3u_catchup_attribute"
    if "/movie/" in path:
        return "vod_movie", "stream_url_path"
    if "/series/" in path:
        return "series_episode", "stream_url_path"
    if re.search(r"\bs\d{1,2}\s*e\d{1,3}\b", title):
        return "series_episode", "title_episode_pattern"
    if any(token in f" {group} " for token in [" vod ", " movie ", " movies ", " film ", " cinema "]):
        return "vod_movie", "group_title_token"
    if any(token in f" {group} " for token in [" series ", " tv series ", " shows "]):
        return "series", "group_title_token"
    if row.get("stream_url_private"):
        return "live_tv", "m3u_stream_record_default"
    return "unknown", "no_deterministic_signal"


def bool_flag(text: str, patterns: list[str]) -> str:
    key = normalize_token(text)
    return "Y" if any(re.search(pattern, key) for pattern in patterns) else ""


def load_xtream_metadata(latest_raw: Path) -> dict[str, Any]:
    categories: dict[str, str] = {}
    stream_by_id: dict[str, dict[str, str]] = {}
    for file_name in ("player_api_live_categories.json", "player_api_vod_categories.json", "player_api_series_categories.json"):
        path = latest_raw / file_name
        if not path.exists():
            continue
        payload = load_json(path, [])
        for item in payload if isinstance(payload, list) else []:
            category_id = str(item.get("category_id", ""))
            if category_id:
                categories[category_id] = normalize_space(item.get("category_name", ""))
    for file_name, item_type in [("player_api_live_streams.json", "live_tv"), ("player_api_vod_streams.json", "vod_movie"), ("player_api_series.json", "series")]:
        path = latest_raw / file_name
        if not path.exists():
            continue
        payload = load_json(path, [])
        for item in payload if isinstance(payload, list) else []:
            stream_id = str(item.get("stream_id") or item.get("series_id") or "")
            category_id = str(item.get("category_id", ""))
            if stream_id:
                stream_by_id[stream_id] = {
                    "item_type": item_type,
                    "category_id": category_id,
                    "category_name": categories.get(category_id, ""),
                    "stream_id": str(item.get("stream_id", "")),
                    "series_id": str(item.get("series_id", "")),
                }
    return {"categories": categories, "stream_by_id": stream_by_id}


def build_xtream_stream_url(urls: dict[str, str], item: dict[str, Any], item_type: str) -> str:
    api_base = urls.get("api_base", "")
    parsed = urllib.parse.urlsplit(api_base)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    username = query.get("username", "")
    password = query.get("password", "")
    if not parsed.scheme or not parsed.netloc or not username or not password:
        return ""
    server = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
    if item_type == "live_tv":
        return f"{server}/live/{urllib.parse.quote(username)}/{urllib.parse.quote(password)}/{item.get('stream_id')}.m3u8"
    if item_type == "vod_movie":
        extension = normalize_space(item.get("container_extension", "")) or "mp4"
        return f"{server}/movie/{urllib.parse.quote(username)}/{urllib.parse.quote(password)}/{item.get('stream_id')}.{extension}"
    return ""


def xtream_api_rows(repo_root: Path, profile: dict[str, Any], dataset_timestamp: str, latest_raw: Path, refs: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    xtream = load_xtream_metadata(latest_raw)
    categories = xtream["categories"]
    urls = resolve_source_urls(repo_root, profile["source_key"])
    inputs = [
        ("player_api_live_streams.json", "live_tv", "stream_id"),
        ("player_api_vod_streams.json", "vod_movie", "stream_id"),
        ("player_api_series.json", "series", "series_id"),
    ]
    rows: list[dict[str, str]] = []
    for file_name, item_type, id_field in inputs:
        path = latest_raw / file_name
        if not path.exists():
            continue
        payload = load_json(path, [])
        if not isinstance(payload, list):
            continue
        for item in payload:
            source_number = len(rows) + 1
            name = normalize_space(item.get("name", ""))
            category_id = str(item.get("category_id") or "")
            category_name = categories.get(category_id, "")
            stream_url = build_xtream_stream_url(urls, item, item_type)
            stream = parse_stream_url(stream_url) if stream_url else {"scheme": "", "host": "", "path": "", "extension": "", "stream_id_candidate": "", "redacted_url": ""}
            network = match_network(refs, [name, category_name])
            country_raw, country_norm, country_method, country_conf = deterministic_country(" ".join([name, category_name]))
            if not country_norm and network.get("country"):
                country_raw = network.get("country", "")
                country_norm = country_raw
                country_method = "repo_reference_network_country"
                country_conf = network.get("confidence", "0")
            lang_raw, lang_norm, lang_method, lang_conf = deterministic_language(" ".join([name, category_name]))
            row = {field: "" for field in ALL_STREAM_FIELDS}
            row.update(
                {
                    "source_key": profile["source_key"],
                    "source_display_name": profile.get("source_display_name", ""),
                    "source_type": profile.get("source_type", ""),
                    "dataset_timestamp": dataset_timestamp,
                    "record_key": f"{profile['source_key']}:{dataset_timestamp}:api:{source_number:08d}",
                    "source_record_number": str(source_number),
                    "raw_title": name,
                    "normalized_title": name,
                    "item_type": item_type,
                    "item_type_reason": "xtream_api_metadata",
                    "tvg_id": normalize_space(item.get("epg_channel_id", "")),
                    "tvg_name": name,
                    "tvg_logo": normalize_space(item.get("stream_icon") or item.get("cover") or ""),
                    "group_title": category_name,
                    "group_path": category_name,
                    "group_content_token": category_name,
                    "stream_url_private": stream_url,
                    "stream_url_redacted": stream.get("redacted_url", ""),
                    "stream_scheme": stream.get("scheme", ""),
                    "stream_host": stream.get("host", ""),
                    "stream_path": stream.get("path", ""),
                    "stream_extension": stream.get("extension", ""),
                    "stream_id_candidate": stream.get("stream_id_candidate", ""),
                    "xtream_category_id": category_id,
                    "xtream_category_name": category_name,
                    "xtream_stream_id": str(item.get("stream_id", "")),
                    "xtream_series_id": str(item.get("series_id", "")),
                    "network_raw": network["raw"],
                    "network_normalized": network["normalized"],
                    "network_country": network["country"],
                    "network_match_method": network["method"],
                    "network_match_confidence": network["confidence"],
                    "country_raw": country_raw,
                    "country_normalized": country_norm,
                    "country_derivation_method": country_method,
                    "language_raw": lang_raw,
                    "language_normalized": lang_norm,
                    "language_derivation_method": lang_method,
                    "is_hd": bool_flag(f"{name} {category_name}", [r"\bhd\b"]),
                    "is_fhd": bool_flag(f"{name} {category_name}", [r"\bfhd\b", r"1080p"]),
                    "is_uhd": bool_flag(f"{name} {category_name}", [r"\buhd\b"]),
                    "is_4k": bool_flag(f"{name} {category_name}", [r"\b4k\b"]),
                    "is_backup": bool_flag(f"{name} {category_name}", [r"\bbackup\b", r"\bbak\b"]),
                    "is_hevc": bool_flag(f"{name} {category_name}", [r"\bhevc\b", r"\bh265\b", r"\bx265\b"]),
                    "is_catchup": "Y" if str(item.get("tv_archive", "")) in {"1", "true", "True"} else "",
                    "is_adult": "Y" if str(item.get("is_adult", "")) in {"1", "true", "True"} else "",
                    "is_sports": bool_flag(f"{name} {category_name}", [r"\bsport", r"\bnfl\b", r"\bnhl\b", r"\bnba\b", r"\bmlb\b"]),
                    "include_candidate": "Y",
                    "notes": f"source_api_file={file_name}; country_confidence={country_conf}; language_confidence={lang_conf}",
                }
            )
            rows.append(row)
    return rows


def parse_m3u_inventory(
    repo_root: Path,
    profile: dict[str, Any],
    dataset_timestamp: str,
    latest_raw: Path,
    refs: dict[str, dict[str, str]],
    allow_xtream_fallback: bool = True,
) -> list[dict[str, str]]:
    path = latest_raw / "playlist.m3u"
    if not path.exists():
        return xtream_api_rows(repo_root, profile, dataset_timestamp, latest_raw, refs) if allow_xtream_fallback else []
    encoding = detect_encoding(path)
    xtream = load_xtream_metadata(latest_raw)
    stream_metadata = xtream["stream_by_id"]
    rows: list[dict[str, str]] = []
    pending: dict[str, Any] | None = None
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.decode(encoding, errors="replace").strip()
            if not line:
                continue
            if line.upper().startswith("#EXTINF:"):
                pending = parse_extinf(line)
                pending["line_number"] = line_number
                continue
            if line.startswith("#"):
                continue
            if not pending:
                pending = {"raw_extinf": "", "raw_title": "", "attributes": {}, "line_number": ""}
            attrs = pending.get("attributes", {})
            stream = parse_stream_url(line)
            raw_title = normalize_space(pending.get("raw_title") or attrs.get("tvg-name") or attrs.get("tvg-id"))
            group_title = normalize_space(attrs.get("group-title", ""))
            region_token, language_token, content_token = derive_group_tokens(group_title)
            base = {
                "source_key": profile["source_key"],
                "source_display_name": profile.get("source_display_name", ""),
                "source_type": profile.get("source_type", ""),
                "dataset_timestamp": dataset_timestamp,
                "record_key": "",
                "source_record_number": str(len(rows) + 1),
                "extinf_line_number": str(pending.get("line_number", "")),
                "stream_url_line_number": str(line_number),
                "raw_extinf": pending.get("raw_extinf", ""),
                "raw_title": raw_title,
                "normalized_title": normalize_space(raw_title),
                "tvg_id": normalize_space(attrs.get("tvg-id", "")),
                "tvg_name": normalize_space(attrs.get("tvg-name", "")),
                "tvg_logo": normalize_space(attrs.get("tvg-logo", "")),
                "group_title": group_title,
                "group_path": group_title,
                "group_region_token": region_token,
                "group_language_token": language_token,
                "group_content_token": content_token,
                "stream_url_private": line,
                "stream_url_redacted": stream["redacted_url"],
                "stream_scheme": stream["scheme"],
                "stream_host": stream["host"],
                "stream_path": stream["path"],
                "stream_extension": stream["extension"],
                "stream_id_candidate": stream["stream_id_candidate"],
                "xtream_category_id": "",
                "xtream_category_name": "",
                "xtream_stream_id": "",
                "xtream_series_id": "",
                "xtream_episode_id": "",
                "is_catchup": "Y" if attrs.get("catchup") else "",
            }
            meta = stream_metadata.get(base["stream_id_candidate"], {})
            base["xtream_category_id"] = meta.get("category_id", "")
            base["xtream_category_name"] = meta.get("category_name", "")
            base["xtream_stream_id"] = meta.get("stream_id", "")
            base["xtream_series_id"] = meta.get("series_id", "")
            item_type, reason = classify_item(base, stream_metadata)
            network = match_network(refs, [base["tvg_name"], raw_title, group_title])
            country_raw, country_norm, country_method, country_conf = deterministic_country(" ".join([group_title, raw_title]))
            if not country_norm and network.get("country"):
                country_raw = network.get("country", "")
                country_norm = country_raw
                country_method = "repo_reference_network_country"
                country_conf = network.get("confidence", "0")
            lang_raw, lang_norm, lang_method, lang_conf = deterministic_language(" ".join([group_title, raw_title]))
            title_group = f"{raw_title} {group_title}"
            row = {field: "" for field in ALL_STREAM_FIELDS}
            row.update(base)
            row.update(
                {
                    "record_key": f"{profile['source_key']}:{dataset_timestamp}:{len(rows) + 1:08d}",
                    "item_type": item_type,
                    "item_type_reason": reason,
                    "network_raw": network["raw"],
                    "network_normalized": network["normalized"],
                    "network_country": network["country"],
                    "network_match_method": network["method"],
                    "network_match_confidence": network["confidence"],
                    "country_raw": country_raw,
                    "country_normalized": country_norm,
                    "country_derivation_method": country_method,
                    "language_raw": lang_raw,
                    "language_normalized": lang_norm,
                    "language_derivation_method": lang_method,
                    "location_raw": region_token,
                    "location_normalized": region_token,
                    "feed_variant": "East" if re.search(r"\b(east|eastern)\b", title_group, re.I) else "West" if re.search(r"\b(west|western|pacific)\b", title_group, re.I) else "",
                    "is_hd": bool_flag(title_group, [r"\bhd\b"]),
                    "is_fhd": bool_flag(title_group, [r"\bfhd\b", r"1080p"]),
                    "is_uhd": bool_flag(title_group, [r"\buhd\b"]),
                    "is_4k": bool_flag(title_group, [r"\b4k\b"]),
                    "is_sd": bool_flag(title_group, [r"\bsd\b"]),
                    "is_backup": bool_flag(title_group, [r"\bbackup\b", r"\bbak\b"]),
                    "is_hevc": bool_flag(title_group, [r"\bhevc\b", r"\bh265\b", r"\bx265\b"]),
                    "is_adult": bool_flag(title_group, [r"\badult\b", r"\bxxx\b", r"\b18\+\b"]),
                    "is_sports": bool_flag(title_group, [r"\bsport", r"\bnfl\b", r"\bnhl\b", r"\bnba\b", r"\bmlb\b"]),
                    "include_candidate": "Y",
                    "exclude_candidate": "",
                    "notes": f"country_confidence={country_conf}; language_confidence={lang_conf}",
                }
            )
            rows.append(row)
            pending = None
    return rows


def xml_child_texts(element: ET.Element, tag_name: str) -> list[str]:
    values: list[str] = []
    for child in list(element):
        if strip_namespace(child.tag) == tag_name and child.text:
            values.append(normalize_space(child.text))
    return values


def xml_first_attr(element: ET.Element, tag_name: str, attr_name: str) -> str:
    for child in list(element):
        if strip_namespace(child.tag) == tag_name and child.attrib.get(attr_name):
            return normalize_space(child.attrib.get(attr_name, ""))
    return ""


def parse_xmltv_time(value: str) -> str:
    if not value:
        return ""
    match = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", value)
    if not match:
        return ""
    base = match.group(1)
    offset = match.group(2) or "+0000"
    try:
        parsed = datetime.strptime(base + offset, "%Y%m%d%H%M%S%z")
        return parsed.astimezone().replace(microsecond=0).isoformat()
    except ValueError:
        return ""


def parse_epg_inventory(profile: dict[str, Any], dataset_timestamp: str, latest_raw: Path, m3u_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    path = latest_raw / "epg.xml"
    if not path.exists():
        return [], []
    tree = ET.parse(path)
    root = tree.getroot()
    by_tvg_id = {normalize_token(row.get("tvg_id", "")): row for row in m3u_rows if row.get("tvg_id")}
    by_name: dict[str, dict[str, str]] = {}
    for row in m3u_rows:
        for name in [row.get("raw_title", ""), row.get("tvg_name", "")]:
            key = normalize_token(name)
            if key and key not in by_name:
                by_name[key] = row
    channel_rows: list[dict[str, str]] = []
    channel_match_by_id: dict[str, dict[str, str]] = {}
    for element in list(root):
        if strip_namespace(element.tag) != "channel":
            continue
        channel_id = normalize_space(element.attrib.get("id", ""))
        display_names = xml_child_texts(element, "display-name")
        match_row = by_tvg_id.get(normalize_token(channel_id))
        method = "tvg_id" if match_row else ""
        if not match_row:
            for name in display_names:
                match_row = by_name.get(normalize_token(name))
                if match_row:
                    method = "display_name"
                    break
        row = {
            "source_key": profile["source_key"],
            "dataset_timestamp": dataset_timestamp,
            "epg_channel_id": channel_id,
            "display_name_primary": display_names[0] if display_names else "",
            "display_names_all": "; ".join(display_names),
            "icon_src": xml_first_attr(element, "icon", "src"),
            "url": "; ".join(xml_child_texts(element, "url")),
            "matched_m3u_record_key": match_row.get("record_key", "") if match_row else "",
            "matched_m3u_title": match_row.get("raw_title", "") if match_row else "",
            "match_method": method or "none",
            "match_confidence": "1.00" if method == "tvg_id" else "0.85" if method else "0",
        }
        channel_rows.append(row)
        if channel_id:
            channel_match_by_id[channel_id] = row
    programme_rows: list[dict[str, str]] = []
    for index, element in enumerate(list(root), start=1):
        if strip_namespace(element.tag) != "programme":
            continue
        channel_id = normalize_space(element.attrib.get("channel", ""))
        start_raw = normalize_space(element.attrib.get("start", ""))
        stop_raw = normalize_space(element.attrib.get("stop", ""))
        start_local = parse_xmltv_time(start_raw)
        stop_local = parse_xmltv_time(stop_raw)
        duration = ""
        try:
            if start_local and stop_local:
                duration = str(int((datetime.fromisoformat(stop_local) - datetime.fromisoformat(start_local)).total_seconds() // 60))
        except ValueError:
            duration = ""
        credits_director: list[str] = []
        credits_actor: list[str] = []
        rating_system = ""
        rating_value = ""
        audio_values: list[str] = []
        subtitle_values: list[str] = []
        for child in list(element):
            tag = strip_namespace(child.tag)
            if tag == "credits":
                credits_director.extend(xml_child_texts(child, "director"))
                credits_actor.extend(xml_child_texts(child, "actor"))
            elif tag == "rating":
                rating_system = normalize_space(child.attrib.get("system", ""))
                rating_value = "; ".join(xml_child_texts(child, "value"))
            elif tag == "audio":
                audio_values.extend([strip_namespace(grand.tag) for grand in list(child)])
            elif tag == "subtitles":
                subtitle_values.append(normalize_space(child.attrib.get("type", "")) or "present")
        channel_match = channel_match_by_id.get(channel_id, {})
        programme_rows.append(
            {
                "source_key": profile["source_key"],
                "dataset_timestamp": dataset_timestamp,
                "programme_key": f"{profile['source_key']}:{dataset_timestamp}:programme:{index:08d}",
                "channel_id": channel_id,
                "matched_m3u_record_key": channel_match.get("matched_m3u_record_key", ""),
                "start_raw": start_raw,
                "stop_raw": stop_raw,
                "start_local": start_local,
                "stop_local": stop_local,
                "duration_minutes": duration,
                "title": "; ".join(xml_child_texts(element, "title")),
                "sub_title": "; ".join(xml_child_texts(element, "sub-title")),
                "desc": "; ".join(xml_child_texts(element, "desc")),
                "category_all": "; ".join(xml_child_texts(element, "category")),
                "episode_num_all": "; ".join(xml_child_texts(element, "episode-num")),
                "episode_num_xmltv_ns": "; ".join(child.text.strip() for child in list(element) if strip_namespace(child.tag) == "episode-num" and child.attrib.get("system") == "xmltv_ns" and child.text),
                "episode_num_onscreen": "; ".join(child.text.strip() for child in list(element) if strip_namespace(child.tag) == "episode-num" and child.attrib.get("system") == "onscreen" and child.text),
                "date": "; ".join(xml_child_texts(element, "date")),
                "country": "; ".join(xml_child_texts(element, "country")),
                "language": "; ".join(xml_child_texts(element, "language")),
                "credits_director": "; ".join(credits_director),
                "credits_actor": "; ".join(credits_actor),
                "rating_system": rating_system,
                "rating_value": rating_value,
                "icon_src": xml_first_attr(element, "icon", "src"),
                "previously_shown": "Y" if any(strip_namespace(child.tag) == "previously-shown" for child in list(element)) else "",
                "premiere": "Y" if any(strip_namespace(child.tag) == "premiere" for child in list(element)) else "",
                "new": "Y" if any(strip_namespace(child.tag) == "new" for child in list(element)) else "",
                "live": "Y" if any(strip_namespace(child.tag) == "live" for child in list(element)) else "",
                "audio": "; ".join(audio_values),
                "subtitles": "; ".join(subtitle_values),
            }
        )
    channel_by_record_key = {channel["matched_m3u_record_key"]: channel for channel in channel_rows if channel.get("matched_m3u_record_key")}
    for row in m3u_rows:
        channel = channel_by_record_key.get(row["record_key"])
        if not channel:
            continue
        row["epg_channel_id_match"] = channel["epg_channel_id"]
        row["epg_display_name_match"] = channel["display_name_primary"]
        row["epg_match_method"] = channel["match_method"]
        row["epg_match_confidence"] = channel["match_confidence"]
    return channel_rows, programme_rows


def write_tsv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=CSV_ENCODING) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_xlsx(path: Path, sheets: dict[str, tuple[list[dict[str, Any]], list[str]]], logger: logging.Logger) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        logger.info("xlsx_skip reason=openpyxl_not_installed")
        return False
    workbook = Workbook()
    first = True
    for name, (rows, columns) in sheets.items():
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        sheet.title = name[:31]
        sheet.append(columns)
        for row in rows:
            sheet.append([row.get(column, "") for column in columns])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return True


def load_scope_rules(scope_dir: Path) -> list[dict[str, str]]:
    path = scope_dir / "scope_rules.tsv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_tsv(path, [], SCOPE_RULE_FIELDS)
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def rule_matches(row: dict[str, str], rule: dict[str, str]) -> bool:
    field = rule.get("field_name", "")
    operator = rule.get("operator", "")
    rule_value = rule.get("value", "")
    actual = row.get(field, "")
    if rule.get("case_sensitive", "").lower() not in {"y", "yes", "true", "1"}:
        actual = actual.lower()
        rule_value = rule_value.lower()
    if operator == "equals":
        return actual == rule_value
    if operator == "contains":
        return rule_value in actual
    if operator == "starts_with":
        return actual.startswith(rule_value)
    if operator == "ends_with":
        return actual.endswith(rule_value)
    if operator == "regex":
        try:
            return re.search(rule_value, actual) is not None
        except re.error:
            return False
    if operator == "in_list":
        values = [value.strip() for value in rule_value.split(",")]
        return actual in values
    if operator == "not_equals":
        return actual != rule_value
    return False


def apply_scope_rules(rows: list[dict[str, str]], rules: list[dict[str, str]]) -> list[dict[str, str]]:
    enabled = [rule for rule in rules if rule.get("enabled", "Y").lower() in {"y", "yes", "true", "1"}]
    include_rules = [rule for rule in enabled if rule.get("action") == "include"]
    exclude_rules = [rule for rule in enabled if rule.get("action") == "exclude"]
    scoped: list[dict[str, str]] = []
    for row in rows:
        copy = dict(row)
        include = True if not include_rules else any(rule_matches(row, rule) for rule in include_rules)
        excluded = any(rule_matches(row, rule) for rule in exclude_rules)
        copy["scope_action"] = "include" if include and not excluded else "exclude"
        copy["scope_reason"] = "matched_rules" if enabled else "no_rules_default_include"
        scoped.append(copy)
    return scoped


def build_extinf(row: dict[str, str]) -> str:
    attrs = []
    for key, field in [("tvg-id", "tvg_id"), ("tvg-name", "tvg_name"), ("tvg-logo", "tvg_logo"), ("group-title", "group_title")]:
        value = normalize_space(row.get(field, ""))
        if value:
            attrs.append(f'{key}="{value.replace(chr(34), chr(39))}"')
    title = normalize_space(row.get("raw_title") or row.get("tvg_name") or row.get("tvg_id") or row.get("record_key"))
    return f"#EXTINF:-1 {' '.join(attrs)},{title}" if attrs else f"#EXTINF:-1,{title}"


def export_filtered_feeds(latest_raw: Path, web_dir: Path, scoped_rows: list[dict[str, str]], epg_channels: list[dict[str, str]]) -> dict[str, Any]:
    web_dir.mkdir(parents=True, exist_ok=True)
    included = [row for row in scoped_rows if row.get("scope_action") == "include" and row.get("stream_url_private")]
    lines = ["#EXTM3U"]
    for row in included:
        lines.append(build_extinf(row))
        lines.append(row["stream_url_private"])
    playlist = "\n".join(lines) + "\n"
    for file_name in ("playlist.m3u", "playlist.m3u8"):
        (web_dir / file_name).write_text(playlist, encoding="utf-8", newline="\n")
    kept_epg_ids = {row.get("epg_channel_id_match", "") for row in included if row.get("epg_channel_id_match")}
    source_epg = latest_raw / "epg.xml"
    if source_epg.exists() and kept_epg_ids:
        tree = ET.parse(source_epg)
        root = tree.getroot()
        for child in list(root):
            tag = strip_namespace(child.tag)
            channel_id = child.attrib.get("id", "") if tag == "channel" else child.attrib.get("channel", "") if tag == "programme" else ""
            if tag in {"channel", "programme"} and channel_id not in kept_epg_ids:
                root.remove(child)
        tree.write(web_dir / "epg.xml", encoding="utf-8", xml_declaration=True)
    else:
        (web_dir / "epg.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>\n', encoding="utf-8")
    manifest = {
        "generated_at": utc_iso(),
        "included_records": len(included),
        "playlist": "playlist.m3u",
        "playlist_m3u8": "playlist.m3u8",
        "epg": "epg.xml",
        "note": "Source-specific output; SmartCDN stable files are not overwritten.",
    }
    write_json(web_dir / "manifest.json", manifest)
    (web_dir / "index.html").write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>IPTV Source Feed</title></head><body><h1>IPTV Source Feed</h1><ul><li><a href="playlist.m3u">playlist.m3u</a></li><li><a href="playlist.m3u8">playlist.m3u8</a></li><li><a href="epg.xml">epg.xml</a></li><li><a href="manifest.json">manifest.json</a></li></ul><p>Generated {html.escape(manifest['generated_at'])}</p></body></html>""",
        encoding="utf-8",
    )
    return manifest


def parse_source(
    repo_root: Path,
    source_key: str,
    export_xlsx: bool = True,
    export_feeds: bool = True,
    parse_m3u: bool = True,
    parse_epg: bool = True,
    parse_xtream: bool = True,
) -> dict[str, Any]:
    key = clean_source_key(source_key)
    stamp = utc_stamp()
    paths = source_paths(repo_root, key, stamp)
    logger = configure_logger(repo_root, "source_parse", "source_parse.log.txt")
    profile = load_public_profiles(repo_root).get(key)
    if not profile:
        raise ValueError(f"Unknown source profile: {key}")
    logger.info(
        "parse_start source_key=%s timestamp=%s parse_m3u=%s parse_epg=%s parse_xtream=%s",
        key,
        stamp,
        parse_m3u,
        parse_epg,
        parse_xtream,
    )
    refs = load_reference_networks(repo_root)
    if parse_m3u:
        m3u_rows = parse_m3u_inventory(repo_root, profile, stamp, paths.latest_raw, refs, allow_xtream_fallback=parse_xtream)
    elif parse_xtream:
        m3u_rows = xtream_api_rows(repo_root, profile, stamp, paths.latest_raw, refs)
    else:
        m3u_rows = []
    if parse_epg:
        epg_channels, epg_programmes = parse_epg_inventory(profile, stamp, paths.latest_raw, m3u_rows)
    else:
        epg_channels, epg_programmes = [], []
    scope_rules = load_scope_rules(paths.scope_dir)
    scoped_rows = apply_scope_rules(m3u_rows, scope_rules)
    group_counts = Counter((row.get("group_title", ""), row.get("item_type", "")) for row in m3u_rows)
    group_summary = [
        {"source_key": key, "dataset_timestamp": stamp, "group_title": group, "item_type": item_type, "record_count": str(count)}
        for (group, item_type), count in sorted(group_counts.items())
    ]
    network_audit = [
        {
            "source_key": key,
            "dataset_timestamp": stamp,
            "record_key": row["record_key"],
            "candidate_text": " | ".join(filter(None, [row.get("tvg_name", ""), row.get("raw_title", ""), row.get("group_title", "")])),
            "network_normalized": row.get("network_normalized", ""),
            "network_country": row.get("network_country", ""),
            "match_method": row.get("network_match_method", ""),
            "match_confidence": row.get("network_match_confidence", ""),
        }
        for row in m3u_rows
    ]
    country_language_audit = [
        {
            "source_key": key,
            "dataset_timestamp": stamp,
            "record_key": row["record_key"],
            "country_raw": row.get("country_raw", ""),
            "country_normalized": row.get("country_normalized", ""),
            "country_derivation_method": row.get("country_derivation_method", ""),
            "country_confidence": re.search(r"country_confidence=([^;]+)", row.get("notes", "")).group(1) if re.search(r"country_confidence=([^;]+)", row.get("notes", "")) else "",
            "language_raw": row.get("language_raw", ""),
            "language_normalized": row.get("language_normalized", ""),
            "language_derivation_method": row.get("language_derivation_method", ""),
            "language_confidence": re.search(r"language_confidence=([^;]+)", row.get("notes", "")).group(1) if re.search(r"language_confidence=([^;]+)", row.get("notes", "")) else "",
        }
        for row in m3u_rows
    ]
    local_fetch_manifest = []
    for file_name in ["playlist.m3u", "epg.xml", *XTREAM_FETCH_TARGETS.keys()]:
        local_path = paths.latest_raw / file_name
        if local_path.exists():
            local_fetch_manifest.append(
                {
                    "source_key": key,
                    "dataset_timestamp": stamp,
                    "file_label": file_name,
                    "url_redacted": "",
                    "latest_path": str(local_path),
                    "snapshot_path": "",
                    "bytes": str(local_path.stat().st_size),
                    "sha256": sha256_file(local_path),
                    "status": "local_existing_file",
                    "error": "",
                }
            )
    outputs = {
        "all_stream_records.tsv": (m3u_rows, ALL_STREAM_FIELDS),
        "live_tv_channels.tsv": ([row for row in m3u_rows if row.get("item_type") == "live_tv"], ALL_STREAM_FIELDS),
        "vod_movies.tsv": ([row for row in m3u_rows if row.get("item_type") == "vod_movie"], ALL_STREAM_FIELDS),
        "series.tsv": ([row for row in m3u_rows if row.get("item_type") == "series"], ALL_STREAM_FIELDS),
        "series_episodes.tsv": ([row for row in m3u_rows if row.get("item_type") == "series_episode"], ALL_STREAM_FIELDS),
        "epg_channels.tsv": (epg_channels, EPG_CHANNEL_FIELDS),
        "epg_programmes.tsv": (epg_programmes, EPG_PROGRAMME_FIELDS),
        "m3u_group_summary.tsv": (group_summary, GROUP_SUMMARY_FIELDS),
        "network_match_audit.tsv": (network_audit, NETWORK_AUDIT_FIELDS),
        "country_language_audit.tsv": (country_language_audit, COUNTRY_LANGUAGE_AUDIT_FIELDS),
        "scope_candidates.tsv": (scoped_rows, SCOPE_CANDIDATE_FIELDS),
    }
    parse_manifest: list[dict[str, str]] = []
    for folder in (paths.latest_report, paths.snapshot_report):
        if not (folder / "source_fetch_manifest.tsv").exists():
            write_tsv(folder / "source_fetch_manifest.tsv", local_fetch_manifest, FETCH_MANIFEST_FIELDS)
        for file_name, (rows, columns) in outputs.items():
            out_path = folder / file_name
            write_tsv(out_path, rows, columns)
            parse_manifest.append(
                {
                    "source_key": key,
                    "dataset_timestamp": stamp,
                    "artifact": file_name,
                    "path": str(out_path),
                    "rows": str(len(rows)),
                    "status": "ok",
                    "notes": f"parse_m3u={parse_m3u}; parse_epg={parse_epg}; parse_xtream={parse_xtream}",
                }
            )
    write_tsv(paths.scope_dir / "scope_candidates.tsv", scoped_rows, SCOPE_CANDIDATE_FIELDS)
    if not (paths.scope_dir / "focused_channels.tsv").exists():
        write_tsv(paths.scope_dir / "focused_channels.tsv", [row for row in scoped_rows if row.get("scope_action") == "include"], SCOPE_CANDIDATE_FIELDS)
    feed_manifest = {"included_records": 0}
    if export_feeds:
        feed_manifest = export_filtered_feeds(paths.latest_raw, paths.web_feed_dir, scoped_rows, epg_channels)
        parse_manifest.append({"source_key": key, "dataset_timestamp": stamp, "artifact": "source_specific_feeds", "path": str(paths.web_feed_dir), "rows": str(feed_manifest.get("included_records", 0)), "status": "ok", "notes": "SmartCDN files untouched"})
    else:
        parse_manifest.append({"source_key": key, "dataset_timestamp": stamp, "artifact": "source_specific_feeds", "path": str(paths.web_feed_dir), "rows": "0", "status": "skipped", "notes": "Feed export skipped by user"})
    for folder in (paths.latest_report, paths.snapshot_report):
        write_tsv(folder / "source_parse_manifest.tsv", parse_manifest, PARSE_MANIFEST_FIELDS)
    xlsx_path = paths.latest_report / "iptv_inventory_review.xlsx"
    xlsx_created = False
    if export_xlsx:
        xlsx_created = write_xlsx(
            xlsx_path,
            {
                "All Streams": (m3u_rows, ALL_STREAM_FIELDS),
                "EPG Channels": (epg_channels, EPG_CHANNEL_FIELDS),
                "EPG Programmes": (epg_programmes, EPG_PROGRAMME_FIELDS),
                "Scope Candidates": (scoped_rows, SCOPE_CANDIDATE_FIELDS),
            },
            logger,
        )
    update_profile_status(repo_root, key, last_parse_at=utc_iso(), source_status="parsed")
    logger.info(
        "parse_complete source_key=%s rows=%s epg_channels=%s epg_programmes=%s reports=%s xlsx=%s",
        key,
        len(m3u_rows),
        len(epg_channels),
        len(epg_programmes),
        paths.latest_report,
        xlsx_created,
    )
    return {
        "source_key": key,
        "dataset_timestamp": stamp,
        "all_stream_records": len(m3u_rows),
        "live_tv_channels": sum(1 for row in m3u_rows if row.get("item_type") == "live_tv"),
        "vod_movies": sum(1 for row in m3u_rows if row.get("item_type") == "vod_movie"),
        "series": sum(1 for row in m3u_rows if row.get("item_type") == "series"),
        "series_episodes": sum(1 for row in m3u_rows if row.get("item_type") == "series_episode"),
        "epg_channels": len(epg_channels),
        "epg_programmes": len(epg_programmes),
        "latest_report": str(paths.latest_report),
        "web_feed_dir": str(paths.web_feed_dir),
        "feed_exported": export_feeds,
        "xlsx_path": str(xlsx_path) if xlsx_created else "",
    }


def local_dataset_status(repo_root: Path, source_key: str) -> dict[str, Any]:
    paths = source_paths(repo_root, source_key, "status")
    files = [
        paths.latest_raw / "playlist.m3u",
        paths.latest_raw / "epg.xml",
        *[paths.latest_raw / file_name for file_name in XTREAM_FETCH_TARGETS],
    ]
    return {
        "source_key": clean_source_key(source_key),
        "latest_raw": str(paths.latest_raw),
        "latest_report": str(paths.latest_report),
        "files": [
            {"path": str(path), "exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}
            for path in files
        ],
    }


def validate_source_workflow(repo_root: Path, source_key: str | None = None) -> dict[str, Any]:
    ensure_base_files(repo_root)
    profiles = load_public_profiles(repo_root)
    keys = [clean_source_key(source_key)] if source_key else sorted(profiles)
    errors: list[str] = []
    warnings: list[str] = []
    public_path = profile_public_path(repo_root)
    try:
        load_json(public_path, {})
    except Exception as exc:
        errors.append(f"public_profile_json_parse_error:{exc}")
    private_path = profile_private_path(repo_root)
    if private_path.exists():
        ignored = os.popen(f'git -C "{repo_root}" check-ignore "data/source_profiles/source_profiles.private.json"').read().strip()
        if not ignored:
            errors.append("private_profile_json_is_not_gitignored")
    for key in keys:
        if key not in profiles:
            errors.append(f"unknown_source_key:{key}")
            continue
        paths = source_paths(repo_root, key, "validation")
        if not paths.latest_raw.exists():
            warnings.append(f"latest_raw_missing:{key}")
        playlist = paths.latest_raw / "playlist.m3u"
        epg = paths.latest_raw / "epg.xml"
        if playlist.exists():
            text = playlist.read_text(encoding=detect_encoding(playlist), errors="replace")
            if not text.lstrip("\ufeff").startswith("#EXTM3U"):
                errors.append(f"m3u_missing_extm3u:{key}")
            extinf = len(re.findall(r"(?m)^#EXTINF:", text))
            streams = len([line for line in text.splitlines() if line.strip() and not line.startswith("#")])
            if extinf and streams and extinf != streams:
                warnings.append(f"m3u_extinf_stream_count_mismatch:{key}:{extinf}:{streams}")
        if epg.exists():
            try:
                root = ET.parse(epg).getroot()
                channels = sum(1 for child in list(root) if strip_namespace(child.tag) == "channel")
                programmes = sum(1 for child in list(root) if strip_namespace(child.tag) == "programme")
                if channels == 0:
                    warnings.append(f"epg_channel_count_zero:{key}")
                if programmes == 0:
                    warnings.append(f"epg_programme_count_zero:{key}")
            except ET.ParseError as exc:
                errors.append(f"epg_xml_parse_error:{key}:{exc}")
        required = [
            "all_stream_records.tsv",
            "live_tv_channels.tsv",
            "vod_movies.tsv",
            "series.tsv",
            "series_episodes.tsv",
            "epg_channels.tsv",
            "epg_programmes.tsv",
            "m3u_group_summary.tsv",
            "network_match_audit.tsv",
            "country_language_audit.tsv",
            "source_fetch_manifest.tsv",
            "source_parse_manifest.tsv",
            "scope_candidates.tsv",
        ]
        for file_name in required:
            path = paths.latest_report / file_name
            if not path.exists():
                warnings.append(f"required_tsv_missing:{key}:{file_name}")
                continue
            first = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0] if path.stat().st_size else ""
            if "\t" not in first and file_name not in {"source_fetch_manifest.tsv", "source_parse_manifest.tsv"}:
                errors.append(f"tsv_header_not_tab_delimited:{key}:{file_name}")
    smartcdn_files = [repo_root / "web" / "feeds" / name for name in ("smartcdn.m3u", "smartcdn.m3u8", "smartcdn.xml", "smartcdn.eml")]
    for path in smartcdn_files:
        if not path.exists():
            warnings.append(f"smartcdn_file_missing:{path.as_posix()}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "profile_count": len(profiles)}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Multi-source IPTV inventory workflow")
    parser.add_argument("command", choices=["init", "fetch", "parse", "validate", "status"])
    parser.add_argument("--repo-root", type=Path, default=repo_root_from_here())
    parser.add_argument("--source-key", default="")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if args.command == "init":
        ensure_base_files(repo_root)
        print(profile_public_path(repo_root))
        return 0
    if args.command == "fetch":
        print(json.dumps(fetch_source(repo_root, args.source_key), indent=2))
        return 0
    if args.command == "parse":
        print(json.dumps(parse_source(repo_root, args.source_key), indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(local_dataset_status(repo_root, args.source_key), indent=2))
        return 0
    if args.command == "validate":
        result = validate_source_workflow(repo_root, args.source_key or None)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
