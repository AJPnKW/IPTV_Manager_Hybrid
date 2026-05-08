#!/usr/bin/env python3
"""Read-only IPTV repo/folder census.

Creates a timestamped evidence bundle for canonical repo decision work.
This script does not modify any census target. It only writes under the
IPTV_Manager_Hybrid reports bundle directory.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import shutil
import subprocess
import sys
import traceback
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PRIMARY_REPO = Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid")
OUTPUT_ROOT = PRIMARY_REPO / "reports" / "active_progress" / "bundles" / "iptv_master_census"

TARGETS = [
    {
        "name": "IPTV_Manager_Hybrid",
        "path": Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid"),
        "candidate_role": "canonical_candidate",
    },
    {
        "name": "iptv_control_plane",
        "path": Path(r"C:\Users\andrew\PROJECTS\GitHub\iptv_control_plane"),
        "candidate_role": "canonical_candidate",
    },
    {
        "name": "M3U_Manager-v3",
        "path": Path(r"C:\Users\andrew\PROJECTS\GitHub\M3U_Manager-v3"),
        "candidate_role": "canonical_candidate",
    },
    {
        "name": "iptv",
        "path": Path(r"C:\Users\andrew\PROJECTS\iptv"),
        "candidate_role": "canonical_candidate",
    },
    {
        "name": "iptv_quarantine",
        "path": Path(r"C:\Users\andrew\PROJECTS\iptv_quarantine"),
        "candidate_role": "quarantine",
    },
    {
        "name": "get_xmltvlisting",
        "path": Path(r"C:\Users\andrew\PROJECTS\GitHub\get_xmltvlisting"),
        "candidate_role": "production_external",
    },
]


CODE_EXTS = {
    ".py",
    ".ps1",
    ".psm1",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".sql",
    ".bat",
    ".cmd",
    ".sh",
    ".b4j",
    ".bas",
}
SCRIPT_EXTS = {".py", ".ps1", ".psm1", ".bat", ".cmd", ".sh", ".js", ".ts"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".cfg", ".conf", ".xml"}
DATA_EXTS = {".csv", ".json", ".jsonl", ".xlsx", ".xls", ".tsv", ".db", ".sqlite", ".txt"}
DOC_EXTS = {".md", ".txt", ".html", ".pdf", ".docx", ".xlsx"}
M3U_EXTS = {".m3u", ".m3u8"}
XMLTV_EXTS = {".xml", ".gz"}
LOG_EXTS = {".log", ".txt"}

SECRET_NAME_TOKENS = (
    "secret",
    "token",
    "credential",
    "credentials",
    "password",
    "passwd",
    "apikey",
    "api_key",
    "key",
    ".env",
)
MAPPING_TOKENS = (
    "map",
    "mapping",
    "rosetta",
    "alias",
    "channel",
    "tvg",
    "xmltv",
    "scope",
    "decision",
    "group",
)
QA_TOKENS = (
    "qa",
    "test",
    "report",
    "validation",
    "validate",
    "coverage",
    "duplicate",
    "dedupe",
    "health",
    "parity",
    "summary",
)
OUTPUT_TOKENS = (
    "output",
    "out",
    "ouput",
    "publish",
    "snapshot",
    "release",
    "deploy",
    "bundle",
    "export",
)
DOC_TOKENS = (
    "readme",
    "doc",
    "design",
    "blueprint",
    "workflow",
    "decision",
    "architecture",
    "workbook",
    "state",
)
APP_DIR_TOKENS = ("app", "backend", "frontend", "src", "web")
CONFIG_DIR_TOKENS = ("config",)
DATA_DIR_TOKENS = ("data", "input", "inputs", "manifests", "records")
DOC_DIR_TOKENS = ("docs", ".my_notes")
REPORT_DIR_TOKENS = ("report", "reports")
LOG_DIR_TOKENS = ("log", "logs")


class Logger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8", newline="")

    def log(self, message: str) -> None:
        line = f"{dt.datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        self.handle.write(line + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except OSError:
        return None


def run_git(root: Path, args: List[str]) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


def is_git_repo(root: Path) -> bool:
    ok, output = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    return ok and output.strip().lower() == "true"


def extension_for(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".xml.gz"):
        return ".xml.gz"
    if name.endswith(".log.txt"):
        return ".log.txt"
    return path.suffix.lower()


def normalized_parts(path: Path) -> List[str]:
    return [part.lower() for part in path.parts]


def has_token(value: str, tokens: Iterable[str]) -> bool:
    lower = value.lower()
    return any(token in lower for token in tokens)


def classify_file(path: Path, rel: str) -> Dict[str, bool]:
    lower_rel = rel.lower()
    name = path.name.lower()
    ext = extension_for(path)
    parts = normalized_parts(Path(rel))

    is_m3u = ext in M3U_EXTS
    is_xmltv = (
        ext == ".xml.gz"
        or ext == ".xml"
        or (ext == ".gz" and ("epg" in lower_rel or "xmltv" in lower_rel))
    )
    is_code = ext in CODE_EXTS
    is_script = ext in SCRIPT_EXTS or has_token(name, ("run_", "build_", "execute_", "fetch_", "scan_"))
    is_config = ext in CONFIG_EXTS or any(part in CONFIG_DIR_TOKENS for part in parts)
    is_data = ext in DATA_EXTS or any(part in DATA_DIR_TOKENS for part in parts)
    is_mapping = has_token(lower_rel, MAPPING_TOKENS)
    is_qa = has_token(lower_rel, QA_TOKENS) or any(part in REPORT_DIR_TOKENS for part in parts)
    is_doc = ext in DOC_EXTS and (has_token(lower_rel, DOC_TOKENS) or any(part in DOC_DIR_TOKENS for part in parts))
    is_output = has_token(lower_rel, OUTPUT_TOKENS) or any(part in REPORT_DIR_TOKENS for part in parts)
    is_log = ext in LOG_EXTS and any(part in LOG_DIR_TOKENS for part in parts)
    is_secret_risk = has_token(name, SECRET_NAME_TOKENS)

    return {
        "code": is_code,
        "script": is_script,
        "config_data": is_config or is_data,
        "m3u_xmltv": is_m3u or is_xmltv,
        "mapping": is_mapping,
        "qa_report": is_qa,
        "doc_design": is_doc,
        "output": is_output,
        "log": is_log,
        "secret_risk": is_secret_risk,
    }


def file_record(repo_name: str, root: Path, path: Path, stat: os.stat_result, categories: Dict[str, bool]) -> Dict[str, Any]:
    rel = relpath(path, root)
    return {
        "repo": repo_name,
        "path": str(root),
        "relative_path": rel,
        "file_name": path.name,
        "extension": extension_for(path),
        "size_bytes": stat.st_size,
        "modified_iso": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "category_code": categories["code"],
        "category_script": categories["script"],
        "category_config_data": categories["config_data"],
        "category_m3u_xmltv": categories["m3u_xmltv"],
        "category_mapping": categories["mapping"],
        "category_qa_report": categories["qa_report"],
        "category_doc_design": categories["doc_design"],
        "category_output": categories["output"],
        "category_log": categories["log"],
    }


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def list_to_cell(items: List[str], limit: int = 12) -> str:
    visible = items[:limit]
    suffix = "" if len(items) <= limit else f"; ... ({len(items) - limit} more)"
    return "; ".join(visible) + suffix


def scan_repo(target: Dict[str, Any], logger: Logger) -> Dict[str, Any]:
    name = target["name"]
    root = target["path"]
    logger.log(f"[{name}] Start census: {root}")
    result: Dict[str, Any] = {
        "target": target,
        "exists": root.exists(),
        "readable": False,
        "error": "",
        "git": {},
        "file_count": 0,
        "folder_count": 0,
        "size_bytes": 0,
        "largest": [],
        "newest": [],
        "extension_counts": Counter(),
        "top_level": [],
        "top_dirs": Counter(),
        "rows": defaultdict(list),
        "risks": [],
        "category_counts": Counter(),
    }

    if not root.exists():
        result["error"] = "Path does not exist"
        logger.log(f"[{name}] Missing path")
        return result

    try:
        children = list(root.iterdir())
        result["readable"] = True
        result["top_level"] = sorted(child.name for child in children)
    except OSError as exc:
        result["error"] = f"Unreadable root: {exc}"
        logger.log(f"[{name}] Unreadable root: {exc}")
        return result

    git_repo = is_git_repo(root)
    branch = ""
    remotes = ""
    dirty = ""
    latest_hash = ""
    latest_date = ""
    if git_repo:
        _, branch = run_git(root, ["branch", "--show-current"])
        _, remotes = run_git(root, ["remote", "-v"])
        _, dirty = run_git(root, ["status", "--short"])
        _, latest_hash = run_git(root, ["rev-parse", "HEAD"])
        _, latest_date = run_git(root, ["log", "-1", "--format=%cI"])
    result["git"] = {
        "git_repo": git_repo,
        "branch": branch,
        "remotes": remotes.replace("\n", " | "),
        "dirty_state": "dirty" if dirty else "clean",
        "dirty_details": dirty.replace("\n", " | "),
        "latest_commit_hash": latest_hash,
        "latest_commit_date": latest_date,
    }

    largest: List[Tuple[int, str]] = []
    newest: List[Tuple[float, str]] = []

    try:
        for current_root, dirnames, filenames in os.walk(root, topdown=True):
            current = Path(current_root)
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".pytest_cache", "node_modules"}]
            result["folder_count"] += len(dirnames)

            for dirname in dirnames:
                dir_rel = relpath(current / dirname, root)
                top = Path(dir_rel).parts[0] if Path(dir_rel).parts else dirname
                result["top_dirs"][top] += 1

            for filename in filenames:
                path = current / filename
                stat = safe_stat(path)
                if stat is None:
                    result["risks"].append(
                        {
                            "repo": name,
                            "risk_type": "unreadable_file",
                            "severity": "medium",
                            "relative_path": relpath(path, root),
                            "note": "File metadata could not be read",
                        }
                    )
                    continue

                result["file_count"] += 1
                result["size_bytes"] += stat.st_size
                rel = relpath(path, root)
                ext = extension_for(path)
                result["extension_counts"][ext or "[no extension]"] += 1
                categories = classify_file(path, rel)
                record = file_record(name, root, path, stat, categories)

                for category, enabled in categories.items():
                    if enabled:
                        result["category_counts"][category] += 1

                if categories["code"] or categories["script"]:
                    result["rows"]["code"].append(record)
                if categories["config_data"]:
                    result["rows"]["config_data"].append(record)
                if categories["m3u_xmltv"]:
                    result["rows"]["m3u_xmltv"].append(record)
                if categories["mapping"]:
                    result["rows"]["mapping"].append(record)
                if categories["qa_report"]:
                    result["rows"]["qa_report"].append(record)
                if categories["doc_design"]:
                    result["rows"]["doc_design"].append(record)
                if categories["output"]:
                    result["rows"]["output"].append(record)
                if categories["log"]:
                    result["rows"]["log"].append(record)

                if categories["secret_risk"]:
                    result["risks"].append(
                        {
                            "repo": name,
                            "risk_type": "possible_secret_filename",
                            "severity": "high",
                            "relative_path": rel,
                            "note": "Filename suggests possible credentials/secrets. Contents were not read.",
                        }
                    )

                largest.append((stat.st_size, rel))
                newest.append((stat.st_mtime, rel))

        largest.sort(reverse=True)
        newest.sort(reverse=True)
        result["largest"] = largest[:20]
        result["newest"] = newest[:20]

        if name == "get_xmltvlisting":
            result["risks"].append(
                {
                    "repo": name,
                    "risk_type": "production_boundary",
                    "severity": "high",
                    "relative_path": "",
                    "note": "Active production XMLTV output repo. Keep separate; consume outputs or wrap only.",
                }
            )
        if name == "iptv_quarantine":
            result["risks"].append(
                {
                    "repo": name,
                    "risk_type": "quarantine_boundary",
                    "severity": "high",
                    "relative_path": "",
                    "note": "Quarantine/archive material is not first-class source-of-truth.",
                }
            )
        if "ouput" in [item.lower() for item in result["top_level"]]:
            result["risks"].append(
                {
                    "repo": name,
                    "risk_type": "typo_output_folder",
                    "severity": "low",
                    "relative_path": "ouput",
                    "note": "Typo folder exists and was inventoried only; not renamed.",
                }
            )
        if "report" in [item.lower() for item in result["top_level"]]:
            result["risks"].append(
                {
                    "repo": name,
                    "risk_type": "singular_report_folder",
                    "severity": "low",
                    "relative_path": "report",
                    "note": "Old singular report folder exists and was inventoried only; output bundle uses reports/.",
                }
            )
    except Exception as exc:
        result["error"] = f"Scan error: {exc}"
        logger.log(f"[{name}] Scan error: {exc}")
        logger.log(traceback.format_exc())

    logger.log(
        f"[{name}] Done: files={result['file_count']} folders={result['folder_count']} size={result['size_bytes']} bytes"
    )
    return result


def score_candidate(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    target = result["target"]
    name = target["name"]
    if target["candidate_role"] == "production_external":
        return {
            "repo": name,
            "path": str(target["path"]),
            "scored_as_candidate": "false",
            "existing_structure": "",
            "current_useful_code": "",
            "design_completeness": "",
            "migration_risk": "",
            "source_of_truth_readiness": "",
            "production_safety": "",
            "git_health": "",
            "long_term_fit": "",
            "total_score": "",
            "ranking_note": "Production external dependency only. Do not merge now.",
        }
    if target["candidate_role"] != "canonical_candidate":
        return None

    top = {item.lower() for item in result["top_level"]}
    cats = result["category_counts"]
    risks = result["risks"]
    git = result["git"]

    structure = 0
    structure += 1 if any(item in top for item in ("app", "backend", "frontend", "src", "web")) else 0
    structure += 1 if "config" in top else 0
    structure += 1 if any(item in top for item in ("data", "input", "inputs", "manifests")) else 0
    structure += 1 if "docs" in top else 0
    structure += 1 if "scripts" in top else 0
    structure = min(structure, 5)

    useful_code = min(5, int(cats["code"] > 0) + int(cats["script"] > 0) + min(3, cats["code"] // 5))
    design = min(5, int(cats["doc_design"] > 0) + int(cats["mapping"] > 0) + int(cats["qa_report"] > 0) + min(2, cats["doc_design"] // 4))

    bulk_penalty = 0
    if result["file_count"] > 10000:
        bulk_penalty += 2
    elif result["file_count"] > 3000:
        bulk_penalty += 1
    if any(r["risk_type"] in {"typo_output_folder", "singular_report_folder"} for r in risks):
        bulk_penalty += 1
    migration_risk = max(1, 5 - bulk_penalty)

    readiness = min(
        5,
        int(cats["m3u_xmltv"] > 0)
        + int(cats["mapping"] > 0)
        + int(cats["config_data"] > 0)
        + int(cats["qa_report"] > 0)
        + int(cats["output"] > 0),
    )

    production_safety = 4
    if name == "iptv":
        production_safety = 3
    if any("production" in r["risk_type"] for r in risks):
        production_safety = 2

    git_health = 0
    if git.get("git_repo"):
        git_health += 2
        git_health += 1 if git.get("latest_commit_hash") else 0
        git_health += 1 if git.get("remotes") else 0
        git_health += 1 if git.get("dirty_state") == "clean" else 0
    else:
        git_health = 1
    git_health = min(git_health, 5)

    long_term = round((structure + useful_code + design + readiness + production_safety) / 5)
    total = structure + useful_code + design + migration_risk + readiness + production_safety + git_health + long_term

    return {
        "repo": name,
        "path": str(target["path"]),
        "scored_as_candidate": "true",
        "existing_structure": structure,
        "current_useful_code": useful_code,
        "design_completeness": design,
        "migration_risk": migration_risk,
        "source_of_truth_readiness": readiness,
        "production_safety": production_safety,
        "git_health": git_health,
        "long_term_fit": long_term,
        "total_score": total,
        "ranking_note": "Evidence score; higher is better. Review with generated inventories before final canonical decision.",
    }


def treatment_for(result: Dict[str, Any]) -> Dict[str, str]:
    name = result["target"]["name"]
    if name == "get_xmltvlisting":
        return {
            "recommended_treatment": "keep separate",
            "migration_priority": "P0 external",
            "migration_value_notes": "Production XMLTV outputs, lineup registry, publish scripts, integration contract points.",
            "do_not_reuse_notes": "Do not absorb or refactor production logic until tested wrapper/replacement exists.",
            "recommended_next_action": "Record output contract and wrapper points only.",
        }
    if name == "iptv_quarantine":
        return {
            "recommended_treatment": "quarantine",
            "migration_priority": "P4",
            "migration_value_notes": "Possible promoted source roots if backed by QA/manifests.",
            "do_not_reuse_notes": "Pending review bulk, non-IPTV XML/app/icon files, duplicates, untrusted archive material.",
            "recommended_next_action": "Keep as evidence; extract only with explicit source log and QA.",
        }
    if name == "IPTV_Manager_Hybrid":
        return {
            "recommended_treatment": "canonical candidate",
            "migration_priority": "P0",
            "migration_value_notes": "Leading candidate pending census: app structure, backend, configs, docs, reports, pipeline/design work.",
            "do_not_reuse_notes": "Bulk repos/cache/output piles without review; typo folders as final layout.",
            "recommended_next_action": "Score against other candidates and decide canonical from evidence.",
        }
    if name == "iptv_control_plane":
        return {
            "recommended_treatment": "selectively extract",
            "migration_priority": "P1",
            "migration_value_notes": "Control-plane reports, manifests, orchestration scripts, pipeline state.",
            "do_not_reuse_notes": "Any canonical claim before scorecard decision; generated artifacts without retention rules.",
            "recommended_next_action": "Compare as workstream/source donor.",
        }
    if name == "M3U_Manager-v3":
        return {
            "recommended_treatment": "selectively extract",
            "migration_priority": "P3",
            "migration_value_notes": "Small M3U editor, import/export UX, filtering, URL validator concept.",
            "do_not_reuse_notes": "Whole standalone static app as canonical architecture.",
            "recommended_next_action": "Mine for UI/validation ideas only.",
        }
    if name == "iptv":
        return {
            "recommended_treatment": "selectively extract",
            "migration_priority": "P1",
            "migration_value_notes": "Curated inputs, free EPG, legacy review inputs, inventory/research.",
            "do_not_reuse_notes": "Temp/downloads/collected upstream repos wholesale.",
            "recommended_next_action": "Drain source registries and curated inputs after canonical decision.",
        }
    return {
        "recommended_treatment": "ignore",
        "migration_priority": "P9",
        "migration_value_notes": "",
        "do_not_reuse_notes": "",
        "recommended_next_action": "",
    }


def summarize_contract_points(result: Dict[str, Any]) -> str:
    rows = result["rows"]
    if result["target"]["name"] != "get_xmltvlisting":
        return ""
    scripts = [row["relative_path"] for row in rows["code"] if row["relative_path"].lower().startswith("tools")]
    outputs = [
        row["relative_path"]
        for row in rows["m3u_xmltv"]
        if row["relative_path"].lower().startswith("iptv")
    ]
    return (
        "Production boundary: external daily XMLTV output repo. "
        f"Likely scripts: {list_to_cell(sorted(scripts), 10)}. "
        f"Likely outputs: {list_to_cell(sorted(outputs), 12)}."
    )


def build_summary(results: List[Dict[str, Any]], score_rows: List[Dict[str, Any]], bundle_dir: Path, zip_path: Path) -> str:
    scored = [row for row in score_rows if row.get("scored_as_candidate") == "true"]
    scored.sort(key=lambda row: int(row["total_score"]), reverse=True)
    leader = scored[0]["repo"] if scored else "none"
    hybrid = next((row for row in scored if row["repo"] == "IPTV_Manager_Hybrid"), None)
    hybrid_leading = leader == "IPTV_Manager_Hybrid"

    lines = [
        "# IPTV Master Census Summary",
        "",
        f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Output folder: `{bundle_dir}`",
        f"Zip: `{zip_path}`",
        "",
        "## High-Level Findings",
        "",
    ]
    for result in results:
        treatment = treatment_for(result)
        lines.append(
            f"- **{result['target']['name']}**: exists={result['exists']}, git={result['git'].get('git_repo', False)}, "
            f"files={result['file_count']}, folders={result['folder_count']}, treatment={treatment['recommended_treatment']}."
        )
        if result["target"]["name"] == "get_xmltvlisting":
            lines.append(f"  - {summarize_contract_points(result)}")
        if result["error"]:
            lines.append(f"  - Issue: {result['error']}")

    lines.extend(
        [
            "",
            "## Provisional Scorecard",
            "",
            "| Rank | Repo | Total | Note |",
            "|---:|---|---:|---|",
        ]
    )
    for idx, row in enumerate(scored, start=1):
        lines.append(f"| {idx} | {row['repo']} | {row['total_score']} | {row['ranking_note']} |")

    lines.extend(
        [
            "",
            "## Production Boundary",
            "",
            "`get_xmltvlisting` was not scored as a canonical candidate. It remains production-separate and should only be consumed through an output contract or wrapper until a tested replacement exists.",
            "",
            "## Provisional Conclusion",
            "",
        ]
    )
    if hybrid:
        lines.append(
            f"`IPTV_Manager_Hybrid` score: {hybrid['total_score']}. "
            f"Remains leading candidate: {'yes' if hybrid_leading else 'no'}."
        )
    else:
        lines.append("`IPTV_Manager_Hybrid` was not scored due to a census issue.")
    lines.append("")
    lines.append("This bundle is read-only evidence for the planning thread. No migration or cleanup was performed.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_dir = OUTPUT_ROOT / timestamp
    bundle_dir.mkdir(parents=True, exist_ok=False)
    logger = Logger(bundle_dir / "execution.log.txt")
    zip_path = OUTPUT_ROOT / f"{timestamp}.zip"

    try:
        logger.log("IPTV master census started")
        logger.log(f"Primary repo: {PRIMARY_REPO}")
        logger.log(f"Output bundle: {bundle_dir}")

        results = [scan_repo(target, logger) for target in TARGETS]

        identity_rows: List[Dict[str, Any]] = []
        missing_rows: List[Dict[str, Any]] = []
        risk_rows: List[Dict[str, Any]] = []
        migration_rows: List[Dict[str, Any]] = []
        score_rows: List[Dict[str, Any]] = []

        category_rows = {
            "code": [],
            "config_data": [],
            "m3u_xmltv": [],
            "mapping": [],
            "qa_report": [],
            "doc_design": [],
            "output": [],
        }

        for result in results:
            target = result["target"]
            git = result["git"]
            largest = [f"{rel} ({size} bytes)" for size, rel in result["largest"]]
            newest = [
                f"{rel} ({dt.datetime.fromtimestamp(mtime).isoformat(timespec='seconds')})"
                for mtime, rel in result["newest"]
            ]
            treatment = treatment_for(result)
            contract = summarize_contract_points(result)

            identity_rows.append(
                {
                    "repo": target["name"],
                    "path": str(target["path"]),
                    "exists": result["exists"],
                    "readable": result["readable"],
                    "git_repo": git.get("git_repo", False),
                    "branch": git.get("branch", ""),
                    "remotes": git.get("remotes", ""),
                    "dirty_state": git.get("dirty_state", ""),
                    "dirty_details": git.get("dirty_details", ""),
                    "latest_commit_hash": git.get("latest_commit_hash", ""),
                    "latest_commit_date": git.get("latest_commit_date", ""),
                    "total_file_count": result["file_count"],
                    "total_folder_count": result["folder_count"],
                    "approx_size_bytes": result["size_bytes"],
                    "largest_files": list_to_cell(largest, 10),
                    "newest_files": list_to_cell(newest, 10),
                    "recommended_treatment": treatment["recommended_treatment"],
                    "production_risk_notes": contract if target["name"] == "get_xmltvlisting" else "",
                    "migration_value_notes": treatment["migration_value_notes"],
                    "error": result["error"],
                }
            )

            if (not result["exists"]) or (not result["readable"]) or result["error"]:
                missing_rows.append(
                    {
                        "repo": target["name"],
                        "path": str(target["path"]),
                        "exists": result["exists"],
                        "readable": result["readable"],
                        "issue": result["error"] or "Path missing or unreadable",
                    }
                )

            for category in category_rows:
                category_rows[category].extend(result["rows"][category])

            for risk in result["risks"]:
                risk_rows.append(risk)

            migration_rows.append(
                {
                    "repo": target["name"],
                    "path": str(target["path"]),
                    **treatment,
                    "risk_count": len(result["risks"]),
                    "file_count": result["file_count"],
                    "m3u_xmltv_count": result["category_counts"]["m3u_xmltv"],
                    "mapping_count": result["category_counts"]["mapping"],
                    "qa_report_count": result["category_counts"]["qa_report"],
                    "doc_design_count": result["category_counts"]["doc_design"],
                }
            )

            score = score_candidate(result)
            if score:
                score_rows.append(score)

        write_csv(
            bundle_dir / "repo_identity.csv",
            identity_rows,
            [
                "repo",
                "path",
                "exists",
                "readable",
                "git_repo",
                "branch",
                "remotes",
                "dirty_state",
                "dirty_details",
                "latest_commit_hash",
                "latest_commit_date",
                "total_file_count",
                "total_folder_count",
                "approx_size_bytes",
                "largest_files",
                "newest_files",
                "recommended_treatment",
                "production_risk_notes",
                "migration_value_notes",
                "error",
            ],
        )

        inventory_fields = [
            "repo",
            "path",
            "relative_path",
            "file_name",
            "extension",
            "size_bytes",
            "modified_iso",
            "category_code",
            "category_script",
            "category_config_data",
            "category_m3u_xmltv",
            "category_mapping",
            "category_qa_report",
            "category_doc_design",
            "category_output",
            "category_log",
        ]
        write_csv(bundle_dir / "code_inventory.csv", category_rows["code"], inventory_fields)
        write_csv(bundle_dir / "config_data_inventory.csv", category_rows["config_data"], inventory_fields)
        write_csv(bundle_dir / "m3u_xmltv_inventory.csv", category_rows["m3u_xmltv"], inventory_fields)
        write_csv(bundle_dir / "mapping_assets.csv", category_rows["mapping"], inventory_fields)
        write_csv(bundle_dir / "qa_reports_inventory.csv", category_rows["qa_report"], inventory_fields)
        write_csv(bundle_dir / "docs_design_inventory.csv", category_rows["doc_design"], inventory_fields)
        write_csv(bundle_dir / "outputs_inventory.csv", category_rows["output"], inventory_fields)

        write_csv(
            bundle_dir / "risk_register.csv",
            risk_rows,
            ["repo", "risk_type", "severity", "relative_path", "note"],
        )
        write_csv(
            bundle_dir / "migration_value_matrix.csv",
            migration_rows,
            [
                "repo",
                "path",
                "recommended_treatment",
                "migration_priority",
                "migration_value_notes",
                "do_not_reuse_notes",
                "recommended_next_action",
                "risk_count",
                "file_count",
                "m3u_xmltv_count",
                "mapping_count",
                "qa_report_count",
                "doc_design_count",
            ],
        )
        write_csv(
            bundle_dir / "canonical_candidate_scorecard.csv",
            score_rows,
            [
                "repo",
                "path",
                "scored_as_candidate",
                "existing_structure",
                "current_useful_code",
                "design_completeness",
                "migration_risk",
                "source_of_truth_readiness",
                "production_safety",
                "git_health",
                "long_term_fit",
                "total_score",
                "ranking_note",
            ],
        )
        write_csv(
            bundle_dir / "missing_or_unreadable_paths.csv",
            missing_rows,
            ["repo", "path", "exists", "readable", "issue"],
        )

        tree_lines = ["IPTV Master Census Tree Summary", ""]
        for result in results:
            tree_lines.append(f"## {result['target']['name']}")
            tree_lines.append(f"Path: {result['target']['path']}")
            tree_lines.append(f"Exists: {result['exists']} Readable: {result['readable']}")
            tree_lines.append(f"Files: {result['file_count']} Folders: {result['folder_count']} Size bytes: {result['size_bytes']}")
            tree_lines.append("Top-level entries:")
            for item in result["top_level"][:80]:
                tree_lines.append(f"  - {item}")
            if len(result["top_level"]) > 80:
                tree_lines.append(f"  - ... ({len(result['top_level']) - 80} more)")
            tree_lines.append("Top extensions:")
            for ext, count in result["extension_counts"].most_common(25):
                tree_lines.append(f"  - {ext}: {count}")
            tree_lines.append("Top directory groups:")
            for dirname, count in result["top_dirs"].most_common(25):
                tree_lines.append(f"  - {dirname}: {count}")
            tree_lines.append("")
        (bundle_dir / "tree_summary.txt").write_text("\n".join(tree_lines), encoding="utf-8")

        summary = build_summary(results, score_rows, bundle_dir, zip_path)
        (bundle_dir / "summary_for_chatgpt.md").write_text(summary, encoding="utf-8")

        logger.log("Writing zip archive")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(bundle_dir.parent))

        logger.log(f"Zip archive created: {zip_path}")
        logger.log("IPTV master census completed successfully")
        return 0
    except Exception as exc:
        logger.log(f"Fatal error: {exc}")
        logger.log(traceback.format_exc())
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    sys.exit(main())
