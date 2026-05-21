from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import iptv_multi_source as workflow


APP_NAME = "IPTV Multi-Source Inventory Manager"
APP_VERSION = "1.0.0"


class MultiSourceGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.repo_root = REPO_ROOT
        workflow.ensure_base_files(self.repo_root)
        self.worker_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.profiles = workflow.load_public_profiles(self.repo_root)
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1320x920")
        self.minsize(1120, 780)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        self._build_variables()
        self._build_widgets()
        self._refresh_source_selector()
        self.after(100, self._poll_worker_queue)

    def _build_variables(self) -> None:
        self.source_selector_var = tk.StringVar()
        self.source_display_name_var = tk.StringVar()
        self.source_key_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value="direct_urls")
        self.provider_label_var = tk.StringVar()
        self.server_url_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.m3u_url_var = tk.StringVar()
        self.epg_url_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.redacted_urls_var = tk.StringVar(value="No source selected")
        self.dataset_status_var = tk.StringVar(value="No local dataset selected")
        self.current_step_var = tk.StringVar(value="Ready")
        self.counter_var = tk.StringVar(value="")
        self.rule_action_var = tk.StringVar(value="include")
        self.rule_field_var = tk.StringVar(value="group_title")
        self.rule_operator_var = tk.StringVar(value="contains")
        self.rule_value_var = tk.StringVar()

    def _build_widgets(self) -> None:
        source_frame = ttk.LabelFrame(self, text="Source Profile")
        source_frame.grid(row=0, column=0, padx=12, pady=8, sticky="ew")
        source_frame.columnconfigure(1, weight=1)
        source_frame.columnconfigure(3, weight=1)

        ttk.Label(source_frame, text="Source").grid(row=0, column=0, padx=8, pady=4, sticky="w")
        self.source_selector = ttk.Combobox(source_frame, textvariable=self.source_selector_var, state="readonly", width=36)
        self.source_selector.grid(row=0, column=1, padx=8, pady=4, sticky="ew")
        self.source_selector.bind("<<ComboboxSelected>>", lambda _event: self.load_selected_source())
        ttk.Button(source_frame, text="Add source", command=self.add_source).grid(row=0, column=2, padx=8, pady=4)
        ttk.Button(source_frame, text="Edit source", command=self.load_selected_source).grid(row=0, column=3, padx=8, pady=4, sticky="w")
        ttk.Button(source_frame, text="Save source", command=self.save_source).grid(row=0, column=4, padx=8, pady=4)
        ttk.Button(source_frame, text="Test source", command=self.test_source).grid(row=0, column=5, padx=8, pady=4)

        ttk.Label(source_frame, text="Display name").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.source_display_name_var).grid(row=1, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Source key").grid(row=1, column=2, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.source_key_var).grid(row=1, column=3, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Type").grid(row=1, column=4, padx=8, pady=4, sticky="w")
        ttk.Combobox(source_frame, textvariable=self.source_type_var, state="readonly", values=["direct_urls", "xtream_codes"], width=16).grid(row=1, column=5, padx=8, pady=4, sticky="ew")

        ttk.Label(source_frame, text="Provider label").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.provider_label_var).grid(row=2, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Server URL").grid(row=2, column=2, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.server_url_var).grid(row=2, column=3, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Username").grid(row=2, column=4, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.username_var).grid(row=2, column=5, padx=8, pady=4, sticky="ew")

        ttk.Label(source_frame, text="Password").grid(row=3, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.password_var, show="*").grid(row=3, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="M3U URL").grid(row=3, column=2, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.m3u_url_var).grid(row=3, column=3, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="EPG URL").grid(row=3, column=4, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.epg_url_var).grid(row=3, column=5, padx=8, pady=4, sticky="ew")

        ttk.Label(source_frame, text="Notes").grid(row=4, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.notes_var).grid(row=4, column=1, columnspan=3, padx=8, pady=4, sticky="ew")
        ttk.Button(source_frame, text="Show redacted URLs", command=self.show_redacted_urls).grid(row=4, column=4, padx=8, pady=4)
        ttk.Button(source_frame, text="Show local dataset status", command=self.show_dataset_status).grid(row=4, column=5, padx=8, pady=4)

        ttk.Label(source_frame, textvariable=self.redacted_urls_var).grid(row=5, column=0, columnspan=6, padx=8, pady=4, sticky="w")
        ttk.Label(source_frame, textvariable=self.dataset_status_var).grid(row=6, column=0, columnspan=6, padx=8, pady=4, sticky="w")

        fetch_frame = ttk.LabelFrame(self, text="Fetch")
        fetch_frame.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        for index, (label, command) in enumerate([
            ("Fetch M3U", lambda: self.start_fetch(True, False, False)),
            ("Fetch EPG", lambda: self.start_fetch(False, True, False)),
            ("Fetch Xtream API metadata", lambda: self.start_fetch(False, False, True)),
            ("Fetch all", lambda: self.start_fetch(True, True, True)),
        ]):
            ttk.Button(fetch_frame, text=label, command=command).grid(row=0, column=index, padx=8, pady=6, sticky="w")

        parse_frame = ttk.LabelFrame(self, text="Parse")
        parse_frame.grid(row=2, column=0, padx=12, pady=6, sticky="ew")
        for index, (label, command) in enumerate([
            ("Parse latest local M3U", self.start_parse),
            ("Parse latest local EPG", self.start_parse),
            ("Parse Xtream API data", self.start_parse),
            ("Parse all", self.start_parse),
            ("Export TSV", self.start_parse),
            ("Open latest report folder", self.open_latest_report_folder),
        ]):
            ttk.Button(parse_frame, text=label, command=command).grid(row=0, column=index, padx=8, pady=6, sticky="w")

        scope_frame = ttk.LabelFrame(self, text="Scope / Filter")
        scope_frame.grid(row=3, column=0, padx=12, pady=6, sticky="ew")
        ttk.Label(scope_frame, text="Action").grid(row=0, column=0, padx=8, pady=4, sticky="w")
        ttk.Combobox(scope_frame, textvariable=self.rule_action_var, state="readonly", values=["include", "exclude"], width=10).grid(row=0, column=1, padx=8, pady=4)
        ttk.Label(scope_frame, text="Field").grid(row=0, column=2, padx=8, pady=4, sticky="w")
        fields = [
            "raw_title",
            "normalized_title",
            "network_normalized",
            "country_normalized",
            "language_normalized",
            "group_title",
            "location_normalized",
            "feed_variant",
            "item_type",
        ]
        ttk.Combobox(scope_frame, textvariable=self.rule_field_var, state="readonly", values=fields, width=24).grid(row=0, column=3, padx=8, pady=4)
        ttk.Label(scope_frame, text="Operator").grid(row=0, column=4, padx=8, pady=4, sticky="w")
        ttk.Combobox(scope_frame, textvariable=self.rule_operator_var, state="readonly", values=["equals", "contains", "starts_with", "ends_with", "regex", "in_list", "not_equals"], width=16).grid(row=0, column=5, padx=8, pady=4)
        ttk.Label(scope_frame, text="Value").grid(row=0, column=6, padx=8, pady=4, sticky="w")
        ttk.Entry(scope_frame, textvariable=self.rule_value_var, width=28).grid(row=0, column=7, padx=8, pady=4)
        ttk.Button(scope_frame, text="Save rule", command=self.save_scope_rule).grid(row=0, column=8, padx=8, pady=4)
        ttk.Button(scope_frame, text="Export candidate scope TSV", command=self.start_parse).grid(row=0, column=9, padx=8, pady=4)
        ttk.Button(scope_frame, text="Export filtered M3U + EPG", command=self.start_parse).grid(row=0, column=10, padx=8, pady=4)

        diagnostics_frame = ttk.LabelFrame(self, text="Diagnostics")
        diagnostics_frame.grid(row=4, column=0, padx=12, pady=6, sticky="ew")
        ttk.Button(diagnostics_frame, text="Validate selected source", command=self.validate_selected_source).grid(row=0, column=0, padx=8, pady=6)
        ttk.Button(diagnostics_frame, text="Open source feed folder", command=self.open_source_feed_folder).grid(row=0, column=1, padx=8, pady=6)
        ttk.Button(diagnostics_frame, text="Open source scope folder", command=self.open_source_scope_folder).grid(row=0, column=2, padx=8, pady=6)
        ttk.Button(diagnostics_frame, text="Clear log", command=lambda: self.log_text.delete("1.0", "end")).grid(row=0, column=3, padx=8, pady=6)

        progress_frame = ttk.LabelFrame(self, text="Progress")
        progress_frame.grid(row=5, column=0, padx=12, pady=6, sticky="ew")
        progress_frame.columnconfigure(1, weight=1)
        ttk.Label(progress_frame, textvariable=self.current_step_var).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.counter_var).grid(row=0, column=2, padx=8, pady=4, sticky="e")

        log_frame = ttk.LabelFrame(self, text="Errors / Warnings / Counts")
        log_frame.grid(row=6, column=0, padx=12, pady=8, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", height=18)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.append_log(f"{APP_NAME} {APP_VERSION}")
        self.append_log(f"Repo root: {self.repo_root}")

    def append_log(self, text: str) -> None:
        self.log_text.insert("end", f"{workflow.utc_iso()}  {text}\n")
        self.log_text.see("end")

    def selected_source_key(self) -> str:
        value = self.source_selector_var.get() or self.source_key_var.get()
        return workflow.clean_source_key(value.split(" | ", 1)[0])

    def _refresh_source_selector(self) -> None:
        self.profiles = workflow.load_public_profiles(self.repo_root)
        values = [f"{key} | {profile.get('source_display_name', '')}" for key, profile in sorted(self.profiles.items())]
        self.source_selector.configure(values=values)
        if values and not self.source_selector_var.get():
            self.source_selector_var.set(values[0])
            self.load_selected_source()

    def add_source(self) -> None:
        for variable in [
            self.source_display_name_var,
            self.source_key_var,
            self.provider_label_var,
            self.server_url_var,
            self.username_var,
            self.password_var,
            self.m3u_url_var,
            self.epg_url_var,
            self.notes_var,
        ]:
            variable.set("")
        self.source_type_var.set("direct_urls")
        self.redacted_urls_var.set("New source profile")
        self.dataset_status_var.set("")

    def load_selected_source(self) -> None:
        key = self.selected_source_key()
        profile = self.profiles.get(key, {})
        private = workflow.load_private_profiles(self.repo_root).get(key, {})
        self.source_key_var.set(key)
        self.source_display_name_var.set(profile.get("source_display_name", ""))
        self.source_type_var.set(profile.get("source_type", "direct_urls"))
        self.provider_label_var.set(profile.get("provider_label", ""))
        self.server_url_var.set(private.get("server_url", ""))
        self.username_var.set(private.get("username", ""))
        self.password_var.set(private.get("password", ""))
        self.m3u_url_var.set(private.get("m3u_url", ""))
        self.epg_url_var.set(private.get("epg_url", ""))
        self.notes_var.set(profile.get("notes", ""))
        self.show_redacted_urls()
        self.show_dataset_status()

    def save_source(self) -> None:
        try:
            public = {
                "source_key": self.source_key_var.get(),
                "source_display_name": self.source_display_name_var.get(),
                "source_type": self.source_type_var.get(),
                "provider_label": self.provider_label_var.get(),
                "notes": self.notes_var.get(),
                "source_status": "configured",
            }
            private = {
                "source_key": self.source_key_var.get(),
                "source_type": self.source_type_var.get(),
                "server_url": self.server_url_var.get().strip(),
                "username": self.username_var.get().strip(),
                "password": self.password_var.get(),
                "m3u_url": self.m3u_url_var.get().strip(),
                "epg_url": self.epg_url_var.get().strip(),
            }
            profile = workflow.upsert_source_profile(self.repo_root, public, private)
            self.append_log(f"Saved source profile: {profile['source_key']}")
            self._refresh_source_selector()
            self.source_selector_var.set(f"{profile['source_key']} | {profile.get('source_display_name', '')}")
            self.load_selected_source()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.append_log(f"Save failed: {exc}")

    def show_redacted_urls(self) -> None:
        try:
            key = self.source_key_var.get() or self.selected_source_key()
            urls = workflow.resolve_source_urls(self.repo_root, key)
            self.redacted_urls_var.set(
                f"M3U: {workflow.redact_url(urls.get('m3u_url', ''))} | EPG: {workflow.redact_url(urls.get('epg_url', ''))} | API: {workflow.redact_url(urls.get('api_base', ''))}"
            )
        except Exception as exc:
            self.redacted_urls_var.set(f"Redacted URL check failed: {exc}")

    def show_dataset_status(self) -> None:
        try:
            status = workflow.local_dataset_status(self.repo_root, self.selected_source_key())
            parts = []
            for item in status["files"]:
                if item["exists"]:
                    parts.append(f"{Path(item['path']).name}={item['bytes']:,} bytes")
            self.dataset_status_var.set("Local file exists: " + (", ".join(parts) if parts else "no latest files found"))
        except Exception as exc:
            self.dataset_status_var.set(f"Dataset status failed: {exc}")

    def test_source(self) -> None:
        self.show_redacted_urls()
        urls = workflow.resolve_source_urls(self.repo_root, self.source_key_var.get())
        problems = []
        if self.source_type_var.get() == "xtream_codes":
            for name in ("m3u_url", "epg_url", "api_base"):
                if not urls.get(name).startswith(("http://", "https://")):
                    problems.append(name)
        elif not urls.get("m3u_url").startswith(("http://", "https://")):
            problems.append("m3u_url")
        if problems:
            messagebox.showwarning(APP_NAME, f"Missing or invalid URL fields: {', '.join(problems)}")
            self.append_log(f"Test source found invalid fields: {', '.join(problems)}")
        else:
            self.append_log("Source URL test passed with redacted values only.")

    def _start_worker(self, label: str, target: Any, *args: Any) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_NAME, "A task is already running.")
            return
        self.current_step_var.set(label)
        self.counter_var.set("")
        self.progress.configure(value=5)
        self.worker_thread = threading.Thread(target=self._worker_wrapper, args=(target, args), daemon=True)
        self.worker_thread.start()

    def _worker_wrapper(self, target: Any, args: tuple[Any, ...]) -> None:
        try:
            result = target(*args)
            self.worker_queue.put({"kind": "done", "result": result})
        except Exception as exc:
            self.worker_queue.put({"kind": "error", "error": str(exc), "traceback": traceback.format_exc()})

    def start_fetch(self, fetch_m3u: bool, fetch_epg: bool, fetch_xtream: bool) -> None:
        self.save_source()
        key = self.selected_source_key()
        self.append_log(f"Fetch started for {key}")
        self._start_worker("Fetching source data...", workflow.fetch_source, self.repo_root, key, fetch_m3u, fetch_epg, fetch_xtream)

    def start_parse(self) -> None:
        key = self.selected_source_key()
        self.append_log(f"Parse/export started for {key}")
        self._start_worker("Parsing latest local source data...", workflow.parse_source, self.repo_root, key)

    def save_scope_rule(self) -> None:
        try:
            key = self.selected_source_key()
            paths = workflow.source_paths(self.repo_root, key, "rules")
            rules = workflow.load_scope_rules(paths.scope_dir)
            rules.append(
                {
                    "action": self.rule_action_var.get(),
                    "field_name": self.rule_field_var.get(),
                    "operator": self.rule_operator_var.get(),
                    "value": self.rule_value_var.get(),
                    "case_sensitive": "N",
                    "enabled": "Y",
                    "notes": "Created from GUI",
                }
            )
            workflow.write_tsv(paths.scope_dir / "scope_rules.tsv", rules, workflow.SCOPE_RULE_FIELDS)
            self.append_log(f"Saved scope rule for {key}: {self.rule_action_var.get()} {self.rule_field_var.get()} {self.rule_operator_var.get()} {self.rule_value_var.get()}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def validate_selected_source(self) -> None:
        key = self.selected_source_key()
        self._start_worker("Validating source workflow...", workflow.validate_source_workflow, self.repo_root, key)

    def open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(path))
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def open_latest_report_folder(self) -> None:
        self.open_path(workflow.source_paths(self.repo_root, self.selected_source_key(), "open").latest_report)

    def open_source_feed_folder(self) -> None:
        self.open_path(workflow.source_paths(self.repo_root, self.selected_source_key(), "open").web_feed_dir)

    def open_source_scope_folder(self) -> None:
        self.open_path(workflow.source_paths(self.repo_root, self.selected_source_key(), "open").scope_dir)

    def _poll_worker_queue(self) -> None:
        try:
            while True:
                message = self.worker_queue.get_nowait()
                if message["kind"] == "done":
                    self.progress.configure(value=100)
                    self.current_step_var.set("Complete")
                    result = message.get("result", {})
                    self.counter_var.set(self._counter_text(result))
                    self.append_log(json.dumps(result, indent=2))
                    self.profiles = workflow.load_public_profiles(self.repo_root)
                    self.show_dataset_status()
                else:
                    self.progress.configure(value=0)
                    self.current_step_var.set("Error")
                    self.append_log(message.get("error", "Unknown error"))
                    self.append_log(message.get("traceback", ""))
                    messagebox.showerror(APP_NAME, message.get("error", "Unknown error"))
        except queue.Empty:
            pass
        self.after(100, self._poll_worker_queue)

    def _counter_text(self, result: dict[str, Any]) -> str:
        if "all_stream_records" in result:
            return f"streams={result.get('all_stream_records', 0):,}; epg_channels={result.get('epg_channels', 0):,}; programmes={result.get('epg_programmes', 0):,}"
        if "manifest_rows" in result:
            ok = sum(1 for row in result["manifest_rows"] if row.get("status") == "ok")
            return f"files={ok}/{len(result['manifest_rows'])}"
        if "errors" in result:
            return f"errors={len(result.get('errors', []))}; warnings={len(result.get('warnings', []))}"
        return ""


def main() -> int:
    app = MultiSourceGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
