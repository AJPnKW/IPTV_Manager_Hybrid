#!/usr/bin/env python3
import argparse
import logging
import os
import re
import socket
import ssl
import sys
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import requests

# ------------- CONFIGURATION -------------

# User-Agents to test in order
USER_AGENTS = [
    "Mozilla/5.0",
    "Mozilla/5.0 (Linux; Android 12; TiviMate) AppleWebKit/537.36 (KHTML, like Gecko) ExoPlayer",
    "Mozilla/5.0 (Linux; Android 12; TiviMate) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ExoPlayer",
    "IPTVSmartersPlayer",
]

# Timeouts (seconds)
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 10

# ------------- DATA STRUCTURES -------------

@dataclass
class StreamResult:
    index: int
    raw_line: str
    url: str
    scheme: str
    host: str
    path: str
    is_http_like: bool
    is_udp: bool
    is_rtmp: bool
    is_hls: bool
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    user_agent_used: Optional[str] = None
    error: Optional[str] = None
    geo_block_suspected: bool = False
    vpn_block_suspected: bool = False
    udpxy_required: bool = False
    notes: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["notes"] = "; ".join(self.notes or [])
        return d

# ------------- HELPERS -------------

URL_REGEX = re.compile(r'^(https?://|udp://|rtmp://)', re.IGNORECASE)

def is_url(line: str) -> bool:
    return bool(URL_REGEX.match(line.strip()))

def parse_url(url: str):
    parsed = urlparse(url.strip())
    return parsed.scheme.lower(), parsed.hostname or "", parsed.path or ""

def detect_hls(url: str, content_type: Optional[str]) -> bool:
    if url.lower().endswith(".m3u8"):
        return True
    if content_type and "application/vnd.apple.mpegurl" in content_type.lower():
        return True
    if content_type and "application/x-mpegurl" in content_type.lower():
        return True
    return False

def classify_geo_vpn(status: Optional[int], final_url: Optional[str], body_snippet: str) -> (bool, bool, List[str]):
    notes = []
    geo = False
    vpn = False

    if status in (451,):
        geo = True
        notes.append("HTTP 451 (Unavailable For Legal Reasons) – strong geo-block indicator")

    if status in (403, 401):
        # Could be geo-block, VPN-block, or auth
        if "geo" in body_snippet.lower() or "region" in body_snippet.lower():
            geo = True
            notes.append("403/401 with geo/region hint in body – possible geo-block")
        if "vpn" in body_snippet.lower() or "proxy" in body_snippet.lower():
            vpn = True
            notes.append("403/401 with vpn/proxy hint in body – possible VPN/proxy block")

    if final_url:
        lower = final_url.lower()
        if "geo" in lower or "region" in lower:
            geo = True
            notes.append("Redirect URL suggests geo restriction")
        if "captcha" in lower or "verify" in lower:
            notes.append("Redirect to verification/captcha – may require browser")

    return geo, vpn, notes

def safe_request(url: str, ua: str) -> (Optional[requests.Response], Optional[str]):
    try:
        headers = {"User-Agent": ua}
        resp = requests.get(
            url,
            headers=headers,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
            stream=True,
            verify=True,
        )
        return resp, None
    except requests.exceptions.RequestException as e:
        return None, str(e)

# ------------- CORE ANALYSIS -------------

def analyze_stream(index: int, line: str) -> StreamResult:
    url = line.strip()
    scheme, host, path = parse_url(url)
    is_http_like = scheme in ("http", "https")
    is_udp = scheme == "udp"
    is_rtmp = scheme == "rtmp"

    result = StreamResult(
        index=index,
        raw_line=line.rstrip("\n"),
        url=url,
        scheme=scheme,
        host=host,
        path=path,
        is_http_like=is_http_like,
        is_udp=is_udp,
        is_rtmp=is_rtmp,
        is_hls=False,
        notes=[],
    )

    if is_udp:
        result.udpxy_required = True
        result.notes.append("UDP stream – likely requires udpxy or router multicast support")
        return result

    if is_rtmp:
        result.notes.append("RTMP stream – often deprecated or blocked; many players no longer support it")
        return result

    if not is_http_like:
        result.notes.append("Unknown or unsupported scheme")
        return result

    # HTTP/HTTPS probing with multiple UAs
    for ua in USER_AGENTS:
        resp, err = safe_request(url, ua)
        if err:
            result.notes.append(f"User-Agent '{ua}' failed: {err}")
            continue

        result.http_status = resp.status_code
        result.final_url = resp.url
        result.content_type = resp.headers.get("Content-Type", "")
        result.user_agent_used = ua

        # Read a small snippet to inspect body
        snippet = ""
        try:
            # read small chunk without consuming entire stream
            for chunk in resp.iter_content(chunk_size=2048):
                snippet = chunk.decode(errors="ignore")
                break
        except Exception as e:
            result.notes.append(f"Error reading body snippet: {e}")

        # HLS detection
        result.is_hls = detect_hls(result.final_url or url, result.content_type)

        # Geo/VPN hints
        geo, vpn, extra_notes = classify_geo_vpn(result.http_status, result.final_url, snippet)
        result.geo_block_suspected = geo
        result.vpn_block_suspected = vpn
        result.notes.extend(extra_notes)

        # Basic success heuristic
        if 200 <= result.http_status < 300:
            result.notes.append("HTTP 2xx – stream endpoint reachable")
        elif 300 <= result.http_status < 400:
            result.notes.append("HTTP 3xx – redirected; may still be playable")
        elif 400 <= result.http_status < 500:
            result.notes.append("HTTP 4xx – client-side error; may be auth, geo, VPN, or token issue")
        elif 500 <= result.http_status < 600:
            result.notes.append("HTTP 5xx – server-side error")

        # If we got any response at all, stop trying more UAs
        break

    if result.http_status is None and not result.error:
        result.error = "All User-Agents failed to connect"

    return result

def parse_playlist(path: str) -> List[str]:
    urls = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if is_url(stripped):
                urls.append(stripped)
    return urls

# ------------- LOGGING & REPORTING -------------

def setup_logging(log_path: str):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

def log_results(results: List[StreamResult]):
    for r in results:
        logging.info(f"Index: {r.index}")
        logging.info(f"  URL: {r.url}")
        logging.info(f"  Scheme: {r.scheme}")
        logging.info(f"  Host: {r.host}")
        logging.info(f"  Path: {r.path}")
        logging.info(f"  HTTP-like: {r.is_http_like}")
        logging.info(f"  UDP: {r.is_udp}")
        logging.info(f"  RTMP: {r.is_rtmp}")
        logging.info(f"  HLS: {r.is_hls}")
        logging.info(f"  HTTP status: {r.http_status}")
        logging.info(f"  Final URL: {r.final_url}")
        logging.info(f"  Content-Type: {r.content_type}")
        logging.info(f"  User-Agent used: {r.user_agent_used}")
        logging.info(f"  Geo-block suspected: {r.geo_block_suspected}")
        logging.info(f"  VPN-block suspected: {r.vpn_block_suspected}")
        logging.info(f"  UDPxy required: {r.udpxy_required}")
        logging.info(f"  Notes: {', '.join(r.notes or [])}")
        logging.info("-" * 80)

def generate_html_report(results: List[StreamResult], html_path: str, playlist_name: str):
    total = len(results)
    http_count = sum(1 for r in results if r.is_http_like)
    udp_count = sum(1 for r in results if r.is_udp)
    rtmp_count = sum(1 for r in results if r.is_rtmp)
    hls_count = sum(1 for r in results if r.is_hls)
    geo_suspected = sum(1 for r in results if r.geo_block_suspected)
    vpn_suspected = sum(1 for r in results if r.vpn_block_suspected)
    udpxy_needed = sum(1 for r in results if r.udpxy_required)
    ok_2xx = sum(1 for r in results if r.http_status and 200 <= r.http_status < 300)

    def esc(s: Optional[str]) -> str:
        if s is None:
            return ""
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html>\n<html lang='en'>\n<head>\n")
        f.write("<meta charset='UTF-8'>\n")
        f.write(f"<title>Playlist Analysis Report - {esc(playlist_name)}</title>\n")
        f.write("<style>\n")
        f.write("body { font-family: Arial, sans-serif; margin: 20px; }\n")
        f.write("h1, h2, h3 { color: #333; }\n")
        f.write("table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }\n")
        f.write("th, td { border: 1px solid #ccc; padding: 6px 8px; font-size: 12px; }\n")
        f.write("th { background-color: #f0f0f0; }\n")
        f.write(".ok { background-color: #e6ffe6; }\n")
        f.write(".warn { background-color: #fff8e6; }\n")
        f.write(".bad { background-color: #ffe6e6; }\n")
        f.write("</style>\n</head>\n<body>\n")

        # Title
        f.write(f"<h1>Playlist Analysis Report</h1>\n")
        f.write(f"<h2>Source: {esc(playlist_name)}</h2>\n")

        # Summary section
        f.write("<section id='summary'>\n")
        f.write("<h2>Summary</h2>\n")
        f.write("<table>\n")
        f.write("<tr><th>Metric</th><th>Value</th></tr>\n")
        f.write(f"<tr><td>Total streams</td><td>{total}</td></tr>\n")
        f.write(f"<tr><td>HTTP/HTTPS streams</td><td>{http_count}</td></tr>\n")
        f.write(f"<tr><td>UDP streams</td><td>{udp_count}</td></tr>\n")
        f.write(f"<tr><td>RTMP streams</td><td>{rtmp_count}</td></tr>\n")
        f.write(f"<tr><td>HLS (m3u8) detected</td><td>{hls_count}</td></tr>\n")
        f.write(f"<tr><td>Reachable (HTTP 2xx)</td><td>{ok_2xx}</td></tr>\n")
        f.write(f"<tr><td>Geo-block suspected</td><td>{geo_suspected}</td></tr>\n")
        f.write(f"<tr><td>VPN-block suspected</td><td>{vpn_suspected}</td></tr>\n")
        f.write(f"<tr><td>UDPxy required</td><td>{udpxy_needed}</td></tr>\n")
        f.write("</table>\n")

        f.write("<h3>Key Observations</h3>\n")
        f.write("<ul>\n")
        f.write("<li>Use a compatible User-Agent (e.g., TiviMate + ExoPlayer) for HTTP/HTTPS streams.</li>\n")
        f.write("<li>UDP streams typically require udpxy or router multicast support.</li>\n")
        f.write("<li>Geo-block or VPN-block is inferred from HTTP codes, redirects, and body hints.</li>\n")
        f.write("<li>RTMP streams are often deprecated and may not be playable in modern apps.</li>\n")
        f.write("</ul>\n")
        f.write("</section>\n")

        # Detailed table
        f.write("<section id='details'>\n")
        f.write("<h2>Per-Stream Analysis</h2>\n")
        f.write("<table>\n")
        f.write("<tr>")
        headers = [
            "Index", "URL", "Scheme", "HTTP Status", "Final URL",
            "Content-Type", "HLS", "Geo?", "VPN?", "UDPxy?", "User-Agent Used", "Notes"
        ]
        for h in headers:
            f.write(f"<th>{esc(h)}</th>")
        f.write("</tr>\n")

        for r in results:
            cls = ""
            if r.http_status and 200 <= r.http_status < 300:
                cls = "ok"
            elif r.geo_block_suspected or r.vpn_block_suspected:
                cls = "warn"
            elif r.http_status and r.http_status >= 400:
                cls = "bad"

            f.write(f"<tr class='{cls}'>")
            f.write(f"<td>{r.index}</td>")
            f.write(f"<td>{esc(r.url)}</td>")
            f.write(f"<td>{esc(r.scheme)}</td>")
            f.write(f"<td>{'' if r.http_status is None else r.http_status}</td>")
            f.write(f"<td>{esc(r.final_url or '')}</td>")
            f.write(f"<td>{esc(r.content_type or '')}</td>")
            f.write(f"<td>{'Yes' if r.is_hls else 'No'}</td>")
            f.write(f"<td>{'Yes' if r.geo_block_suspected else 'No'}</td>")
            f.write(f"<td>{'Yes' if r.vpn_block_suspected else 'No'}</td>")
            f.write(f"<td>{'Yes' if r.udpxy_required else 'No'}</td>")
            f.write(f"<td>{esc(r.user_agent_used or '')}</td>")
            f.write(f"<td>{esc('; '.join(r.notes or []))}</td>")
            f.write("</tr>\n")

        f.write("</table>\n")
        f.write("</section>\n")

        f.write("</body>\n</html>\n")

# ------------- MAIN -------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze IPTV playlist URLs for reachability, UA behavior, geo/VPN hints, and udpxy needs."
    )
    parser.add_argument("playlist", help="Path to M3U or text file containing stream URLs")
    parser.add_argument(
        "--log",
        default="playlist_analysis.log.txt",
        help="Path to log file (default: playlist_analysis.log.txt)",
    )
    parser.add_argument(
        "--html",
        default="playlist_report.html",
        help="Path to HTML report (default: playlist_report.html)",
    )
    args = parser.parse_args()

    setup_logging(args.log)
    logging.info(f"Loading playlist from: {args.playlist}")

    if not os.path.isfile(args.playlist):
        logging.error("Playlist file does not exist.")
        sys.exit(1)

    urls = parse_playlist(args.playlist)
    logging.info(f"Found {len(urls)} stream URLs to analyze.")

    results: List[StreamResult] = []
    for idx, line in enumerate(urls, start=1):
        logging.info(f"Analyzing stream #{idx}")
        res = analyze_stream(idx, line)
        results.append(res)

    logging.info("Writing detailed log...")
    log_results(results)

    logging.info("Generating HTML report...")
    generate_html_report(results, args.html, os.path.basename(args.playlist))

    logging.info(f"Done. Log: {args.log} | HTML report: {args.html}")

if __name__ == "__main__":
    main()
