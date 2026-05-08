
#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

VERSION = "1.0.0"
CANONICAL_ROOT = Path(r"C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid")
REPOS_ROOT = CANONICAL_ROOT / "repos"
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_ROOT = CANONICAL_ROOT / "report" / "active_progress" / "bundles" / "iptv_cleanup_census" / RUN_ID
LOG_PATH = RUN_ROOT / "execution.log.txt"
ZIP_PATH = CANONICAL_ROOT / "report" / "active_progress" / "exports" / f"iptv_cleanup_census_{RUN_ID}.zip"

SAFE_JUNK_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".nuxt",
    ".parcel-cache", ".cache", "node_modules", ".venv", "venv", ".tox", ".idea", ".vs",
    ".sass-cache"
}
SAFE_JUNK_FILE_PATTERNS = [
    r".*\.tmp$",
    r".*\.temp$",
    r".*\.bak$",
    r".*\.old$",
    r".*\.orig$",
    r".*\.rej$",
    r"Thumbs\.db$",
    r"desktop\.ini$",
    r".*~$",
]
REVIEW_VERSION_PATTERNS = [
    r".*__[\dA-F]{8}$",
    r".*copy.*",
    r".*backup.*",
    r".*archive.*",
    r".*old.*",
    r".*legacy.*",
    r".*previous.*",
    r".*v\d+.*",
]
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".xml", ".yaml", ".yml", ".m3u", ".m3u8", ".html", ".ps1", ".py", ".js", ".ts"}


def write_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line)


def sha256_small(path: Path, max_bytes: int = 64 * 1024 * 1024) -> str:
    if path.stat().st_size > max_bytes:
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def matches_any(name: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if re.match(pattern, name, flags=re.IGNORECASE):
            return True
    return False


def safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


@dataclass
class RepoSizeRow:
    repo_name: str
    repo_path: str
    total_files: int
    total_dirs: int
    total_bytes: int
    junk_dir_hits: int
    junk_file_hits: int
    review_version_name_hits: int


def main() -> int:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    write_log(f"IPTV cleanup census started. Version={VERSION}")
    write_log(f"Canonical root: {CANONICAL_ROOT}")
    write_log(f"Repos root: {REPOS_ROOT}")

    if not REPOS_ROOT.exists():
        write_log("Repos root does not exist.")
        return 1

    repo_dirs = sorted([p for p in REPOS_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    if not repo_dirs:
        write_log("No repo directories found under repos root.")
        return 1

    repo_size_rows: List[Dict[str, object]] = []
    junk_candidates: List[Dict[str, object]] = []
    review_candidates: List[Dict[str, object]] = []
    duplicate_groups_rows: List[Dict[str, object]] = []
    extension_rows: List[Dict[str, object]] = []
    all_file_rows: List[Dict[str, object]] = []

    ext_counter = Counter()
    duplicate_index: Dict[Tuple[int, str], List[Tuple[str, str]]] = defaultdict(list)

    for repo_dir in repo_dirs:
        write_log(f"Scanning repo: {repo_dir.name}")
        total_files = 0
        total_dirs = 0
        total_bytes = 0
        junk_dir_hits = 0
        junk_file_hits = 0
        review_version_name_hits = 0

        for current_root, dirnames, filenames in os.walk(repo_dir):
            current_root_path = Path(current_root)
            total_dirs += len(dirnames)

            for dirname in list(dirnames):
                rel_dir = safe_rel(current_root_path / dirname, REPOS_ROOT)
                if dirname in SAFE_JUNK_DIRS:
                    junk_dir_hits += 1
                    junk_candidates.append({
                        "repo_name": repo_dir.name,
                        "candidate_type": "safe_junk_directory",
                        "relative_path": rel_dir,
                        "reason": "common cache/build/venv directory",
                        "suggested_action": "delete_from_copy_first"
                    })
                elif matches_any(dirname, REVIEW_VERSION_PATTERNS):
                    review_version_name_hits += 1
                    review_candidates.append({
                        "repo_name": repo_dir.name,
                        "candidate_type": "review_directory_name",
                        "relative_path": rel_dir,
                        "reason": "name suggests duplicate/version/archive/staged content",
                        "suggested_action": "manual_review"
                    })

            for filename in filenames:
                total_files += 1
                file_path = current_root_path / filename
                rel_file = safe_rel(file_path, REPOS_ROOT)
                size_bytes = file_path.stat().st_size
                total_bytes += size_bytes
                ext = file_path.suffix.lower()
                ext_counter[ext or "<none>"] += 1

                if matches_any(filename, SAFE_JUNK_FILE_PATTERNS):
                    junk_file_hits += 1
                    junk_candidates.append({
                        "repo_name": repo_dir.name,
                        "candidate_type": "safe_junk_file",
                        "relative_path": rel_file,
                        "reason": "temp/backup/os-noise filename pattern",
                        "suggested_action": "delete_from_copy_first"
                    })
                elif matches_any(filename, REVIEW_VERSION_PATTERNS):
                    review_version_name_hits += 1
                    review_candidates.append({
                        "repo_name": repo_dir.name,
                        "candidate_type": "review_file_name",
                        "relative_path": rel_file,
                        "reason": "name suggests duplicate/version/archive/staged content",
                        "suggested_action": "manual_review"
                    })

                digest = sha256_small(file_path)
                if digest:
                    duplicate_index[(size_bytes, digest)].append((repo_dir.name, rel_file))

                if ext in TEXT_EXTENSIONS or filename.lower() in {"readme.md", "package.json", "pyproject.toml"}:
                    all_file_rows.append({
                        "repo_name": repo_dir.name,
                        "relative_path": rel_file,
                        "size_bytes": size_bytes,
                        "extension": ext or "<none>"
                    })

        repo_size_rows.append(asdict(RepoSizeRow(
            repo_name=repo_dir.name,
            repo_path=str(repo_dir),
            total_files=total_files,
            total_dirs=total_dirs,
            total_bytes=total_bytes,
            junk_dir_hits=junk_dir_hits,
            junk_file_hits=junk_file_hits,
            review_version_name_hits=review_version_name_hits,
        )))

    group_id = 0
    for (size_bytes, digest), members in sorted(duplicate_index.items(), key=lambda x: (-len(x[1]), -x[0][0])):
        if len(members) < 2:
            continue
        group_id += 1
        for repo_name, rel_path in members:
            duplicate_groups_rows.append({
                "duplicate_group_id": f"dup_{group_id:05d}",
                "size_bytes": size_bytes,
                "sha256": digest,
                "repo_name": repo_name,
                "relative_path": rel_path,
                "suggested_action": "review_then_dedupe"
            })

    for ext, count in sorted(ext_counter.items(), key=lambda x: (-x[1], x[0])):
        extension_rows.append({"extension": ext, "count": count})

    def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    repo_size_csv = RUN_ROOT / "repo_size_summary.csv"
    repo_size_json = RUN_ROOT / "repo_size_summary.json"
    junk_csv = RUN_ROOT / "safe_junk_candidates.csv"
    review_csv = RUN_ROOT / "review_candidates.csv"
    dup_csv = RUN_ROOT / "duplicate_groups.csv"
    ext_csv = RUN_ROOT / "extension_summary.csv"
    file_catalog_csv = RUN_ROOT / "text_and_structured_file_catalog.csv"
    validation_json = RUN_ROOT / "validation_summary.json"

    write_csv(repo_size_csv, repo_size_rows)
    write_json(repo_size_json, repo_size_rows)
    write_csv(junk_csv, junk_candidates)
    write_csv(review_csv, review_candidates)
    write_csv(dup_csv, duplicate_groups_rows)
    write_csv(ext_csv, extension_rows)
    write_csv(file_catalog_csv, all_file_rows)

    validation = {
        "version": VERSION,
        "run_id": RUN_ID,
        "overall_status": "passed",
        "repo_count": len(repo_dirs),
        "outputs": [
            str(repo_size_csv),
            str(repo_size_json),
            str(junk_csv),
            str(review_csv),
            str(dup_csv),
            str(ext_csv),
            str(file_catalog_csv),
            str(LOG_PATH),
        ],
        "zip_path": str(ZIP_PATH),
    }
    write_json(validation_json, validation)

    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in RUN_ROOT.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(RUN_ROOT))

    write_log(f"Repo count: {len(repo_dirs)}")
    write_log(f"Safe junk candidates: {len(junk_candidates)}")
    write_log(f"Review candidates: {len(review_candidates)}")
    write_log(f"Duplicate group rows: {len(duplicate_groups_rows)}")
    write_log(f"Zip export: {ZIP_PATH}")
    write_log("IPTV cleanup census completed successfully.")

    print("")
    print("Completion summary")
    print(f"Run folder: {RUN_ROOT}")
    print(f"Zip export: {ZIP_PATH}")
    input("Press Enter to close...")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        input("Press Enter to close...")
        sys.exit(1)
