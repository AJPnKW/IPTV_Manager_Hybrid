# push_focused_iptv_feeds.py
# Version: 1.1.0
# Purpose: Recover and complete Git publishing for generated IPTV focused M3U/EPG files.
# Expected location: C:\Users\andrew\PROJECTS\GitHub\IPTV_Manager_Hybrid\scripts\push_focused_iptv_feeds.py
# Change notes:
# - Stages outputs\feeds, data\channel_scope, and docs\channel_scope only.
# - Creates a commit only when staged changes exist.
# - Pushes an existing local commit when the GUI commit succeeded but push did not run.
# - Forces staging for outputs\feeds because generated output folders may be ignored by repo cleanup rules.
# - Writes a timestamped log and ZIP bundle under reports\git_publish.
# [CAPABILITY] github_publish_scoped_iptv_feeds_recovery=YES

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_NAME = "Focused IPTV Git Publish Recovery"
APP_VERSION = "1.1.0"
PUBLISH_PATHS = ["outputs/feeds", "data/channel_scope", "docs/channel_scope"]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def get_repo_root() -> Path:
    script_path = Path(__file__).resolve()
    if script_path.parent.name.lower() == "scripts":
        return script_path.parent.parent
    return Path.cwd().resolve()


def ensure_run_paths(repo_root: Path) -> dict[str, Path]:
    timestamp = utc_stamp()
    logs_dir = repo_root / "logs"
    run_dir = repo_root / "reports" / "git_publish" / timestamp
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "logs_dir": logs_dir,
        "run_dir": run_dir,
        "log_file": logs_dir / f"focused_iptv_git_publish_{timestamp}.log.txt",
        "summary_json": run_dir / "git_publish_summary.json",
        "summary_txt": run_dir / "summary.txt",
        "zip_file": run_dir.with_suffix(".zip"),
    }


def configure_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("focused_iptv_git_publish")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


def run_git(repo_root: Path, args: list[str], timeout_seconds: int = 900) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
        env=env,
    )


def require_success(result: subprocess.CompletedProcess[str], action: str) -> None:
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"{action} failed"
        raise RuntimeError(message)


def command_record(label: str, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "label": label,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def get_current_branch(repo_root: Path) -> str:
    result = run_git(repo_root, ["branch", "--show-current"], timeout_seconds=60)
    require_success(result, "git branch --show-current")
    branch = result.stdout.strip()
    if not branch:
        raise RuntimeError("Cannot determine current Git branch")
    return branch


def get_upstream(repo_root: Path) -> str:
    result = run_git(repo_root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout_seconds=60)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_pending_push_count(repo_root: Path) -> int:
    upstream = get_upstream(repo_root)
    if not upstream:
        return 0
    result = run_git(repo_root, ["rev-list", "--count", f"{upstream}..HEAD"], timeout_seconds=60)
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return 0


def push_current_branch(repo_root: Path) -> subprocess.CompletedProcess[str]:
    branch = get_current_branch(repo_root)
    upstream = get_upstream(repo_root)
    if upstream:
        return run_git(repo_root, ["push"], timeout_seconds=900)
    return run_git(repo_root, ["push", "-u", "origin", branch], timeout_seconds=900)


def publish(repo_root: Path, logger: logging.Logger) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []
    logger.info("%s %s", APP_NAME, APP_VERSION)
    logger.info("Repo root: %s", repo_root)

    remote = run_git(repo_root, ["remote", "-v"], timeout_seconds=60)
    commands.append(command_record("git remote -v", remote))
    require_success(remote, "git remote -v")

    status_before = run_git(repo_root, ["status", "--porcelain=v1", "--branch"], timeout_seconds=60)
    commands.append(command_record("git status before", status_before))
    require_success(status_before, "git status before")
    logger.info("Git status before:\n%s", status_before.stdout.strip())

    add_result = run_git(repo_root, ["add", "-f", *PUBLISH_PATHS], timeout_seconds=300)
    commands.append(command_record("git add publish paths", add_result))
    require_success(add_result, "git add publish paths")

    diff_result = run_git(repo_root, ["diff", "--cached", "--name-only"], timeout_seconds=60)
    commands.append(command_record("git diff --cached --name-only", diff_result))
    require_success(diff_result, "git diff --cached --name-only")
    staged_files = [line.strip() for line in diff_result.stdout.splitlines() if line.strip()]

    commit_created = False
    if staged_files:
        message = f"Publish focused IPTV feed files {utc_stamp()}"
        commit_result = run_git(
            repo_root,
            ["-c", "commit.gpgsign=false", "commit", "--no-gpg-sign", "--no-verify", "-m", message],
            timeout_seconds=900,
        )
        commands.append(command_record("git commit", commit_result))
        require_success(commit_result, "git commit")
        commit_created = True
        logger.info("Commit created for %s staged file(s).", len(staged_files))
    else:
        logger.info("No staged publish-file changes found.")

    pending_before_push = get_pending_push_count(repo_root)
    logger.info("Local commits waiting to push before push: %s", pending_before_push)

    push_ran = False
    if commit_created or pending_before_push > 0:
        push_result = push_current_branch(repo_root)
        commands.append(command_record("git push", push_result))
        require_success(push_result, "git push")
        push_ran = True
        logger.info("Git push completed.")
    else:
        logger.info("No commit or pending local commit to push.")

    status_after = run_git(repo_root, ["status", "--porcelain=v1", "--branch"], timeout_seconds=60)
    commands.append(command_record("git status after", status_after))
    require_success(status_after, "git status after")
    pending_after_push = get_pending_push_count(repo_root)

    if pending_after_push > 0:
        raise RuntimeError(f"Push finished but {pending_after_push} local commit(s) are still ahead of upstream")

    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "repo_root": str(repo_root),
        "publish_paths": PUBLISH_PATHS,
        "staged_files": staged_files,
        "commit_created": commit_created,
        "pending_before_push": pending_before_push,
        "push_ran": push_ran,
        "pending_after_push": pending_after_push,
        "status_before": status_before.stdout,
        "status_after": status_after.stdout,
        "commands": commands,
    }


def write_outputs(paths: dict[str, Path], summary: dict[str, Any]) -> None:
    paths["summary_json"].write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"{APP_NAME} {APP_VERSION}",
        f"repo_root: {summary['repo_root']}",
        f"commit_created: {summary['commit_created']}",
        f"push_ran: {summary['push_ran']}",
        f"pending_before_push: {summary['pending_before_push']}",
        f"pending_after_push: {summary['pending_after_push']}",
        "staged_files:",
    ]
    lines.extend([f"- {item}" for item in summary["staged_files"]] or ["- none"])
    paths["summary_txt"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(paths["log_file"], paths["run_dir"] / paths["log_file"].name)
    shutil.make_archive(str(paths["run_dir"]), "zip", root_dir=paths["run_dir"])


def main() -> int:
    repo_root = get_repo_root()
    paths = ensure_run_paths(repo_root)
    logger = configure_logger(paths["log_file"])
    try:
        summary = publish(repo_root, logger)
        summary["run_folder"] = str(paths["run_dir"])
        summary["zip_file"] = str(paths["zip_file"])
        write_outputs(paths, summary)
        logger.info("Run folder: %s", paths["run_dir"])
        logger.info("ZIP: %s", paths["zip_file"])
        logger.info("OK - Git publish state is complete.")
        return 0
    except Exception as exc:
        error_summary = {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "repo_root": str(repo_root),
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "run_folder": str(paths["run_dir"]),
            "zip_file": str(paths["zip_file"]),
        }
        paths["summary_json"].write_text(json.dumps(error_summary, indent=2, ensure_ascii=False), encoding="utf-8")
        paths["summary_txt"].write_text(f"FAILED\n{exc}\n", encoding="utf-8")
        try:
            shutil.copy2(paths["log_file"], paths["run_dir"] / paths["log_file"].name)
            shutil.make_archive(str(paths["run_dir"]), "zip", root_dir=paths["run_dir"])
        except Exception:
            logger.error("Failed to package error outputs:\n%s", traceback.format_exc())
        logger.error("FAILED: %s", exc)
        logger.error("Run folder: %s", paths["run_dir"])
        logger.error("ZIP: %s", paths["zip_file"])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
