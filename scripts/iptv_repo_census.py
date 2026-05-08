#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

VERSION = "1.0.0"
DEFAULT_ROOT = Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid")
DEFAULT_REPOS_DIR = DEFAULT_ROOT / "repos"


@dataclass
class RepoSummary:
    repo_name: str
    repo_path: str
    exists: bool
    is_git_repo: bool
    total_files: int
    total_dirs: int
    top_level_items: str
    script_files: int
    html_files: int
    json_files: int
    csv_files: int
    xml_files: int
    yaml_files: int
    md_files: int
    text_files: int
    image_files: int
    video_files: int
    package_files_found: str
    data_like_dirs_found: str
    docs_like_dirs_found: str
    apps_like_dirs_found: str
    sample_scripts: str
    sample_html: str
    sample_data: str
    likely_role_hint: str


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_log(log_path: Path, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line)


def safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def classify_role(repo_name: str, counters: Counter, dirs_found: Dict[str, List[str]], package_hits: List[str]) -> str:
    name = repo_name.lower()
    if "xmltv" in name:
        return "xmltv_ingest_or_output_pipeline"
    if "m3u" in name:
        return "m3u_mapping_or_ingest_tooling"
    if "quarantine" in name:
        return "quarantine_or_archive_source"
    if "control_plane" in name:
        return "orchestration_docs_reports_or_control_layer"
    if "manager" in name:
        return "candidate_canonical_management_repo"
    if counters[".html"] > 5 and counters[".json"] > 5:
        return "app_or_report_repo_with_structured_data"
    if "docs" in dirs_found and counters[".md"] > 5:
        return "documentation_heavy_repo"
    if any(p in package_hits for p in ["docker-compose.yml", "compose.yml", "docker-compose.yaml"]):
        return "runtime_or_service_stack_repo"
    return "mixed_or_needs_manual_review"


def scan_repo(repo_path: Path) -> Tuple[RepoSummary, List[Dict[str, str]]]:
    if not repo_path.exists():
        summary = RepoSummary(
            repo_name=repo_path.name,
            repo_path=str(repo_path),
            exists=False,
            is_git_repo=False,
            total_files=0,
            total_dirs=0,
            top_level_items="",
            script_files=0,
            html_files=0,
            json_files=0,
            csv_files=0,
            xml_files=0,
            yaml_files=0,
            md_files=0,
            text_files=0,
            image_files=0,
            video_files=0,
            package_files_found="",
            data_like_dirs_found="",
            docs_like_dirs_found="",
            apps_like_dirs_found="",
            sample_scripts="",
            sample_html="",
            sample_data="",
            likely_role_hint="missing_repo_path",
        )
        return summary, []

    top_level_items = [item.name for item in sorted(repo_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))]

    counters: Counter = Counter()
    package_files = {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "Pipfile",
        "Pipfile.lock",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "Makefile",
        "README.md",
    }
    package_hits: List[str] = []
    data_like_dirs: List[str] = []
    docs_like_dirs: List[str] = []
    apps_like_dirs: List[str] = []
    sample_scripts: List[str] = []
    sample_html: List[str] = []
    sample_data: List[str] = []
    file_catalog: List[Dict[str, str]] = []

    total_files = 0
    total_dirs = 0

    interesting_script_exts = {".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".ts", ".psm1"}
    data_exts = {".json", ".csv", ".xml", ".yaml", ".yml", ".m3u", ".m3u8", ".txt"}
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    video_exts = {".mp4", ".mkv", ".mov", ".avi"}
    text_exts = {".txt", ".md", ".log"}

    for current_root, dirnames, filenames in os.walk(repo_path):
        current_root_path = Path(current_root)
        total_dirs += len(dirnames)

        for dirname in dirnames:
            lower = dirname.lower()
            if lower in {"data", "dataset", "datasets", "output", "outputs", "exports", "samples", "fixtures"}:
                data_like_dirs.append(safe_rel(current_root_path / dirname, repo_path))
            if lower in {"docs", "doc", "documentation", "reports", "report"}:
                docs_like_dirs.append(safe_rel(current_root_path / dirname, repo_path))
            if lower in {"app", "apps", "src", "ui", "web", "frontend", "backend"}:
                apps_like_dirs.append(safe_rel(current_root_path / dirname, repo_path))

        for filename in filenames:
            total_files += 1
            file_path = current_root_path / filename
            rel_path = safe_rel(file_path, repo_path)
            suffix = file_path.suffix.lower()

            counters[suffix] += 1

            if filename in package_files:
                package_hits.append(rel_path)

            if suffix in interesting_script_exts and len(sample_scripts) < 12:
                sample_scripts.append(rel_path)
            if suffix == ".html" and len(sample_html) < 12:
                sample_html.append(rel_path)
            if suffix in data_exts and len(sample_data) < 12:
                sample_data.append(rel_path)

            if suffix in interesting_script_exts or suffix in data_exts or suffix == ".html" or filename in package_files:
                file_catalog.append(
                    {
                        "repo_name": repo_path.name,
                        "relative_path": rel_path,
                        "extension": suffix or "<none>",
                        "size_bytes": str(file_path.stat().st_size),
                    }
                )

    summary = RepoSummary(
        repo_name=repo_path.name,
        repo_path=str(repo_path),
        exists=True,
        is_git_repo=(repo_path / ".git").exists(),
        total_files=total_files,
        total_dirs=total_dirs,
        top_level_items=" | ".join(top_level_items[:50]),
        script_files=sum(counters[e] for e in interesting_script_exts),
        html_files=counters[".html"],
        json_files=counters[".json"],
        csv_files=counters[".csv"],
        xml_files=counters[".xml"],
        yaml_files=counters[".yaml"] + counters[".yml"],
        md_files=counters[".md"],
        text_files=sum(counters[e] for e in text_exts),
        image_files=sum(counters[e] for e in image_exts),
        video_files=sum(counters[e] for e in video_exts),
        package_files_found=" | ".join(sorted(set(package_hits))[:50]),
        data_like_dirs_found=" | ".join(sorted(set(data_like_dirs))[:50]),
        docs_like_dirs_found=" | ".join(sorted(set(docs_like_dirs))[:50]),
        apps_like_dirs_found=" | ".join(sorted(set(apps_like_dirs))[:50]),
        sample_scripts=" | ".join(sample_scripts),
        sample_html=" | ".join(sample_html),
        sample_data=" | ".join(sample_data),
        likely_role_hint=classify_role(
            repo_name=repo_path.name,
            counters=counters,
            dirs_found={"data": data_like_dirs, "docs": docs_like_dirs, "apps": apps_like_dirs},
            package_hits=package_hits,
        ),
    )
    return summary, file_catalog


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_tree_text(repos_dir: Path) -> str:
    lines: List[str] = [str(repos_dir)]
    if not repos_dir.exists():
        lines.append("  <missing>")
        return "\n".join(lines)

    for repo in sorted([p for p in repos_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        lines.append(f"├─ {repo.name}")
        children = sorted(list(repo.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
        for child in children[:40]:
            lines.append(f"│  ├─ {child.name}")
        if len(children) > 40:
            lines.append("│  └─ ...")
    return "\n".join(lines)


def zip_folder(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(source_dir))


def main() -> int:
    canonical_root = DEFAULT_ROOT
    repos_dir = DEFAULT_REPOS_DIR

    run_id = now_stamp()
    run_root = canonical_root / "report" / "active_progress" / "bundles" / "iptv_repo_census" / run_id
    log_path = run_root / "execution.log.txt"
    zip_path = canonical_root / "report" / "active_progress" / "exports" / f"iptv_repo_census_{run_id}.zip"

    run_root.mkdir(parents=True, exist_ok=True)

    write_log(log_path, f"IPTV repo census started. Version={VERSION}")
    write_log(log_path, f"Canonical root: {canonical_root}")
    write_log(log_path, f"Repos root: {repos_dir}")

    if not repos_dir.exists():
        write_log(log_path, "Repos directory does not exist.")
        return 1

    repo_dirs = sorted([p for p in repos_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    write_log(log_path, f"Repo directories found: {len(repo_dirs)}")

    summaries: List[RepoSummary] = []
    file_catalog_rows: List[Dict[str, str]] = []

    for index, repo_dir in enumerate(repo_dirs, start=1):
        write_log(log_path, f"[{index}/{len(repo_dirs)}] Scanning repo: {repo_dir.name}")
        summary, catalog = scan_repo(repo_dir)
        summaries.append(summary)
        file_catalog_rows.extend(catalog)

    summary_rows = [asdict(item) for item in summaries]

    summary_json_path = run_root / "repo_census_summary.json"
    summary_csv_path = run_root / "repo_census_summary.csv"
    file_catalog_csv_path = run_root / "repo_file_catalog.csv"
    repos_tree_txt_path = run_root / "repos_tree.txt"
    discovered_counts_json_path = run_root / "repo_census_counts.json"
    validation_summary_path = run_root / "validation_summary.json"

    write_json(summary_json_path, summary_rows)
    write_csv(summary_csv_path, summary_rows)
    write_csv(file_catalog_csv_path, file_catalog_rows)
    write_text(repos_tree_txt_path, build_tree_text(repos_dir))
    write_json(
        discovered_counts_json_path,
        {
            "version": VERSION,
            "run_id": run_id,
            "repo_count": len(repo_dirs),
            "git_repo_count": sum(1 for s in summaries if s.is_git_repo),
            "total_files_scanned": sum(s.total_files for s in summaries),
            "total_dirs_scanned": sum(s.total_dirs for s in summaries),
            "repos_root": str(repos_dir),
        },
    )

    write_json(
        validation_summary_path,
        {
            "version": VERSION,
            "run_id": run_id,
            "overall_status": "passed",
            "repos_root_exists": repos_dir.exists(),
            "repo_count": len(repo_dirs),
            "output_files_created": [
                str(summary_json_path),
                str(summary_csv_path),
                str(file_catalog_csv_path),
                str(repos_tree_txt_path),
                str(discovered_counts_json_path),
                str(log_path),
            ],
            "zip_path": str(zip_path),
        },
    )

    zip_folder(run_root, zip_path)

    write_log(log_path, f"Summary JSON: {summary_json_path}")
    write_log(log_path, f"Summary CSV: {summary_csv_path}")
    write_log(log_path, f"File catalog CSV: {file_catalog_csv_path}")
    write_log(log_path, f"Repos tree TXT: {repos_tree_txt_path}")
    write_log(log_path, f"Validation summary: {validation_summary_path}")
    write_log(log_path, f"Zip export: {zip_path}")
    write_log(log_path, "IPTV repo census completed successfully.")

    print("")
    print("Completion summary")
    print(f"Run folder: {run_root}")
    print(f"Repo count: {len(repo_dirs)}")
    print(f"Zip export: {zip_path}")
    input("Press Enter to close...")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        input("Press Enter to close...")
        sys.exit(1)
