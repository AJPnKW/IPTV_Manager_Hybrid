from __future__ import annotations

import json
import csv
import os
import queue
import subprocess
import sys
import threading
import traceback
import urllib.parse
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
        self.rowconfigure(5, weight=1)
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
        self.profile_mode_var = tk.StringVar(value="Edit selected source")
        self.parse_m3u_var = tk.BooleanVar(value=True)
        self.parse_epg_var = tk.BooleanVar(value=True)
        self.parse_xtream_var = tk.BooleanVar(value=True)
        self.export_tsv_var = tk.BooleanVar(value=True)
        self.export_feeds_var = tk.BooleanVar(value=True)

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
        ttk.Button(source_frame, text="Archive source", command=self.archive_source).grid(row=0, column=6, padx=8, pady=4)
        ttk.Button(source_frame, text="Delete source", command=self.delete_source).grid(row=0, column=7, padx=8, pady=4)

        ttk.Label(source_frame, textvariable=self.profile_mode_var).grid(row=1, column=0, columnspan=8, padx=8, pady=4, sticky="w")

        ttk.Label(source_frame, text="Identity: display name").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        self.display_name_entry = ttk.Entry(source_frame, textvariable=self.source_display_name_var)
        self.display_name_entry.grid(row=2, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Source key").grid(row=2, column=2, padx=8, pady=4, sticky="w")
        self.source_key_entry = ttk.Entry(source_frame, textvariable=self.source_key_var)
        self.source_key_entry.grid(row=2, column=3, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Type").grid(row=2, column=4, padx=8, pady=4, sticky="w")
        ttk.Combobox(source_frame, textvariable=self.source_type_var, state="readonly", values=["direct_urls", "xtream_codes"], width=16).grid(row=2, column=5, padx=8, pady=4, sticky="ew")

        ttk.Label(source_frame, text="Provider label").grid(row=3, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.provider_label_var).grid(row=3, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Xtream: server URL").grid(row=3, column=2, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.server_url_var).grid(row=3, column=3, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Username").grid(row=3, column=4, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.username_var).grid(row=3, column=5, padx=8, pady=4, sticky="ew")

        ttk.Label(source_frame, text="Password").grid(row=4, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.password_var, show="*").grid(row=4, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="Direct URLs: M3U").grid(row=4, column=2, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.m3u_url_var).grid(row=4, column=3, padx=8, pady=4, sticky="ew")
        ttk.Label(source_frame, text="EPG URL").grid(row=4, column=4, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.epg_url_var).grid(row=4, column=5, padx=8, pady=4, sticky="ew")
        ttk.Button(source_frame, text="Parse pasted M3U URL", command=self.apply_pasted_m3u_url).grid(row=4, column=6, columnspan=2, padx=8, pady=4)

        ttk.Label(source_frame, text="Notes").grid(row=5, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(source_frame, textvariable=self.notes_var).grid(row=5, column=1, columnspan=3, padx=8, pady=4, sticky="ew")
        ttk.Button(source_frame, text="Show redacted URLs", command=self.show_redacted_urls).grid(row=5, column=4, padx=8, pady=4)
        ttk.Button(source_frame, text="Show local dataset status", command=self.show_dataset_status).grid(row=5, column=5, padx=8, pady=4)

        ttk.Label(source_frame, text="Required: direct URLs need M3U URL; Xtream Codes needs server URL, username, and password. Source key may be typed or auto-filled from display name.").grid(row=6, column=0, columnspan=8, padx=8, pady=4, sticky="w")
        ttk.Label(source_frame, textvariable=self.redacted_urls_var).grid(row=7, column=0, columnspan=8, padx=8, pady=4, sticky="w")
        ttk.Label(source_frame, textvariable=self.dataset_status_var).grid(row=8, column=0, columnspan=8, padx=8, pady=4, sticky="w")

        fetch_frame = ttk.LabelFrame(self, text="Fetch")
        fetch_frame.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        for index, (label, command) in enumerate([
            ("Fetch M3U", lambda: self.start_fetch(True, False, False)),
            ("Fetch EPG", lambda: self.start_fetch(False, True, False)),
            ("Fetch Xtream API metadata", lambda: self.start_fetch(False, False, True)),
            ("Fetch all", lambda: self.start_fetch(True, True, True)),
        ]):
            ttk.Button(fetch_frame, text=label, command=command).grid(row=0, column=index, padx=8, pady=6, sticky="w")

        work_notebook = ttk.Notebook(self)
        work_notebook.grid(row=2, column=0, padx=12, pady=6, sticky="nsew")
        self.rowconfigure(2, weight=1)
        parse_tab = ttk.Frame(work_notebook)
        scope_tab = ttk.Frame(work_notebook)
        reports_tab = ttk.Frame(work_notebook)
        work_notebook.add(parse_tab, text="Parse")
        work_notebook.add(scope_tab, text="Scope / Filter")
        work_notebook.add(reports_tab, text="Reports")
        self._build_parse_tab(parse_tab)
        self._build_scope_tab(scope_tab)
        self._build_reports_tab(reports_tab)

        diagnostics_frame = ttk.LabelFrame(self, text="Diagnostics")
        diagnostics_frame.grid(row=3, column=0, padx=12, pady=6, sticky="ew")
        ttk.Button(diagnostics_frame, text="Validate selected source", command=self.validate_selected_source).grid(row=0, column=0, padx=8, pady=6)
        ttk.Button(diagnostics_frame, text="Open source feed folder", command=self.open_source_feed_folder).grid(row=0, column=1, padx=8, pady=6)
        ttk.Button(diagnostics_frame, text="Open source scope folder", command=self.open_source_scope_folder).grid(row=0, column=2, padx=8, pady=6)
        ttk.Button(diagnostics_frame, text="Clear log", command=lambda: self.log_text.delete("1.0", "end")).grid(row=0, column=3, padx=8, pady=6)

        progress_frame = ttk.LabelFrame(self, text="Progress")
        progress_frame.grid(row=4, column=0, padx=12, pady=6, sticky="ew")
        progress_frame.columnconfigure(1, weight=1)
        ttk.Label(progress_frame, textvariable=self.current_step_var).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=1, padx=8, pady=4, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.counter_var).grid(row=0, column=2, padx=8, pady=4, sticky="e")

        log_frame = ttk.LabelFrame(self, text="Errors / Warnings / Counts")
        log_frame.grid(row=5, column=0, padx=12, pady=8, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", height=18)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.append_log(f"{APP_NAME} {APP_VERSION}")
        self.append_log(f"Repo root: {self.repo_root}")

    def _build_parse_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="Select the local datasets and outputs to refresh. The parser writes source-specific TSVs and feeds only.").grid(row=0, column=0, columnspan=6, padx=8, pady=6, sticky="w")
        ttk.Checkbutton(parent, text="Latest local M3U", variable=self.parse_m3u_var).grid(row=1, column=0, padx=8, pady=4, sticky="w")
        ttk.Checkbutton(parent, text="Latest local EPG", variable=self.parse_epg_var).grid(row=1, column=1, padx=8, pady=4, sticky="w")
        ttk.Checkbutton(parent, text="Xtream API metadata", variable=self.parse_xtream_var).grid(row=1, column=2, padx=8, pady=4, sticky="w")
        ttk.Checkbutton(parent, text="Export TSV review files (required)", variable=self.export_tsv_var, state="disabled").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        ttk.Checkbutton(parent, text="Export filtered M3U + EPG", variable=self.export_feeds_var).grid(row=2, column=1, padx=8, pady=4, sticky="w")
        ttk.Button(parent, text="Parse selected", command=self.start_parse).grid(row=3, column=0, padx=8, pady=8, sticky="w")
        ttk.Button(parent, text="Open latest report folder", command=self.open_latest_report_folder).grid(row=3, column=1, padx=8, pady=8, sticky="w")
        ttk.Button(parent, text="Load report summary", command=lambda: self.load_report_view("groups")).grid(row=3, column=2, padx=8, pady=8, sticky="w")

    def _build_scope_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
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
            "xtream_category_name",
        ]
        editor = ttk.LabelFrame(parent, text="Add include/exclude rule")
        editor.grid(row=0, column=0, padx=8, pady=6, sticky="ew")
        ttk.Label(editor, text="Action").grid(row=0, column=0, padx=6, pady=4)
        ttk.Combobox(editor, textvariable=self.rule_action_var, state="readonly", values=["include", "exclude"], width=10).grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(editor, text="Field").grid(row=0, column=2, padx=6, pady=4)
        ttk.Combobox(editor, textvariable=self.rule_field_var, state="readonly", values=fields, width=24).grid(row=0, column=3, padx=6, pady=4)
        ttk.Label(editor, text="Operator").grid(row=0, column=4, padx=6, pady=4)
        ttk.Combobox(editor, textvariable=self.rule_operator_var, state="readonly", values=["equals", "contains", "starts_with", "ends_with", "regex", "in_list", "not_equals"], width=16).grid(row=0, column=5, padx=6, pady=4)
        ttk.Label(editor, text="Value").grid(row=0, column=6, padx=6, pady=4)
        ttk.Entry(editor, textvariable=self.rule_value_var, width=32).grid(row=0, column=7, padx=6, pady=4)
        ttk.Button(editor, text="Add rule", command=self.save_scope_rule).grid(row=0, column=8, padx=6, pady=4)
        ttk.Button(editor, text="Remove selected", command=self.remove_selected_scope_rule).grid(row=0, column=9, padx=6, pady=4)
        ttk.Button(editor, text="Reload rules", command=self.load_scope_rules_view).grid(row=0, column=10, padx=6, pady=4)
        ttk.Button(editor, text="Apply rules / export feeds", command=self.start_parse).grid(row=0, column=11, padx=6, pady=4)

        columns = ("action", "field_name", "operator", "value", "enabled", "notes")
        self.scope_rules_tree = ttk.Treeview(parent, columns=columns, show="headings", height=8)
        for column in columns:
            self.scope_rules_tree.heading(column, text=column)
            self.scope_rules_tree.column(column, width=150 if column != "value" else 260, anchor="w")
        self.scope_rules_tree.grid(row=1, column=0, padx=8, pady=6, sticky="nsew")
        parent.rowconfigure(1, weight=1)
        self.clear_tree(self.scope_rules_tree)

    def _build_reports_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, padx=8, pady=6, sticky="ew")
        ttk.Button(controls, text="Groups / categories", command=lambda: self.load_report_view("groups")).grid(row=0, column=0, padx=6, pady=4)
        ttk.Button(controls, text="Live TV channels", command=lambda: self.load_report_view("live")).grid(row=0, column=1, padx=6, pady=4)
        ttk.Button(controls, text="Movies", command=lambda: self.load_report_view("movies")).grid(row=0, column=2, padx=6, pady=4)
        ttk.Button(controls, text="Shows / series", command=lambda: self.load_report_view("series")).grid(row=0, column=3, padx=6, pady=4)
        ttk.Button(controls, text="Open latest report folder", command=self.open_latest_report_folder).grid(row=0, column=4, padx=6, pady=4)

        self.report_tree = ttk.Treeview(parent, show="headings", height=12)
        self.report_tree.grid(row=1, column=0, padx=(8, 0), pady=6, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.report_tree.yview)
        scrollbar.grid(row=1, column=1, padx=(0, 8), pady=6, sticky="ns")
        self.report_tree.configure(yscrollcommand=scrollbar.set)

    def append_log(self, text: str) -> None:
        self.log_text.insert("end", f"{workflow.utc_iso()}  {text}\n")
        self.log_text.see("end")

    def selected_source_key(self) -> str:
        value = self.source_key_var.get() or self.source_selector_var.get()
        return workflow.clean_source_key(value.split(" | ", 1)[0])

    def _refresh_source_selector(self) -> None:
        self.profiles = workflow.load_public_profiles(self.repo_root)
        values = [f"{key} | {profile.get('source_display_name', '')} [{profile.get('source_status', '')}]" for key, profile in sorted(self.profiles.items())]
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
        self.source_selector_var.set("")
        self.source_type_var.set("direct_urls")
        self.profile_mode_var.set("Adding new source: fill identity first, then either Direct URLs or Xtream Codes fields.")
        self.redacted_urls_var.set("New unsaved source. Paste a full Xtream M3U URL into Direct URLs: M3U and click Parse pasted M3U URL, or fill server/username/password.")
        self.dataset_status_var.set("No local dataset until the source is saved and fetched.")
        self.display_name_entry.focus_set()

    def load_selected_source(self) -> None:
        key = self.selected_source_key()
        profile = self.profiles.get(key, {})
        private = workflow.load_private_profiles(self.repo_root).get(key, {})
        self.profile_mode_var.set(f"Editing source: {key} ({profile.get('source_status', 'unknown')})")
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
        if hasattr(self, "scope_rules_tree"):
            self.load_scope_rules_view()

    def apply_pasted_m3u_url(self) -> None:
        m3u_url = self.m3u_url_var.get().strip()
        if not m3u_url:
            messagebox.showinfo(APP_NAME, "Paste the provider M3U URL into the M3U URL field first.")
            return
        parsed = urllib.parse.urlsplit(m3u_url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        if parsed.path.lower().endswith("/get.php") and query.get("username") and query.get("password"):
            self.source_type_var.set("xtream_codes")
            self.server_url_var.set(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/"))
            self.username_var.set(query.get("username", ""))
            self.password_var.set(query.get("password", ""))
            if not self.provider_label_var.get().strip():
                self.provider_label_var.set(parsed.hostname or "")
            if not self.source_display_name_var.get().strip():
                self.source_display_name_var.set(parsed.hostname or "Xtream Provider")
            if not self.source_key_var.get().strip():
                self.source_key_var.set(workflow.clean_source_key(self.source_display_name_var.get()))
            self.redacted_urls_var.set("Parsed Xtream fields from pasted M3U URL. Save source to store credentials locally/private.")
            self.append_log("Parsed pasted M3U URL into Xtream server, username, and password fields.")
            return
        self.source_type_var.set("direct_urls")
        self.redacted_urls_var.set("Pasted URL kept as direct M3U URL.")

    def save_source(self) -> dict[str, Any] | None:
        try:
            if self.m3u_url_var.get().strip() and (not self.server_url_var.get().strip() or not self.username_var.get().strip() or not self.password_var.get()):
                self.apply_pasted_m3u_url()
            if not self.source_key_var.get().strip() and self.source_display_name_var.get().strip():
                self.source_key_var.set(workflow.clean_source_key(self.source_display_name_var.get()))
            if not self.source_key_var.get().strip():
                raise ValueError("source_key is required. Enter Source key, or enter Display name so the app can auto-fill it.")
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
            self.source_selector_var.set(f"{profile['source_key']} | {profile.get('source_display_name', '')} [{profile.get('source_status', '')}]")
            self.load_selected_source()
            return profile
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.append_log(f"Save failed: {exc}")
            return None

    def archive_source(self) -> None:
        try:
            key = self.selected_source_key()
            if not messagebox.askyesno(APP_NAME, f"Archive source profile '{key}'?\n\nFetched data and reports stay on disk."):
                return
            profile = workflow.archive_source_profile(self.repo_root, key)
            self.append_log(f"Archived source profile: {key}")
            self._refresh_source_selector()
            self.source_selector_var.set(f"{key} | {profile.get('source_display_name', '')} [{profile.get('source_status', '')}]")
            self.load_selected_source()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.append_log(f"Archive failed: {exc}")

    def delete_source(self) -> None:
        try:
            key = self.selected_source_key()
            if not messagebox.askyesno(APP_NAME, f"Delete source profile '{key}'?\n\nThis removes public/private profile entries only. Captured datasets, reports, and source-specific feeds are preserved."):
                return
            result = workflow.delete_source_profile(self.repo_root, key, delete_private=True)
            self.append_log(f"Deleted source profile: {json.dumps(result)}")
            self.add_source()
            self._refresh_source_selector()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self.append_log(f"Delete failed: {exc}")

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
        if self.m3u_url_var.get().strip():
            self.apply_pasted_m3u_url()
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
        if self.save_source() is None:
            return
        key = self.selected_source_key()
        self.append_log(f"Fetch started for {key}")
        self._start_worker("Fetching source data...", workflow.fetch_source, self.repo_root, key, fetch_m3u, fetch_epg, fetch_xtream)

    def start_parse(self) -> None:
        if not (self.parse_m3u_var.get() or self.parse_epg_var.get() or self.parse_xtream_var.get()):
            messagebox.showinfo(APP_NAME, "Select at least one local dataset to parse: M3U, EPG, or Xtream API metadata.")
            return
        key = self.selected_source_key()
        self.append_log(f"Parse/export started for {key}")
        self._start_worker(
            "Parsing latest local source data...",
            workflow.parse_source,
            self.repo_root,
            key,
            False,
            self.export_feeds_var.get(),
            self.parse_m3u_var.get(),
            self.parse_epg_var.get(),
            self.parse_xtream_var.get(),
        )

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
            self.load_scope_rules_view()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save the scope rule.\n\nWhat happened: {exc}\n\nWhat to do: choose a source, fill Action, Field, Operator, and Value, then try Add rule again.")

    def load_scope_rules_view(self) -> None:
        if not hasattr(self, "scope_rules_tree"):
            return
        self.clear_tree(self.scope_rules_tree)
        try:
            key = self.selected_source_key()
        except ValueError:
            return
        paths = workflow.source_paths(self.repo_root, key, "rules")
        rules = workflow.load_scope_rules(paths.scope_dir)
        for index, rule in enumerate(rules):
            self.scope_rules_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    rule.get("action", ""),
                    rule.get("field_name", ""),
                    rule.get("operator", ""),
                    rule.get("value", ""),
                    rule.get("enabled", ""),
                    rule.get("notes", ""),
                ),
            )

    def remove_selected_scope_rule(self) -> None:
        try:
            key = self.selected_source_key()
            selected = self.scope_rules_tree.selection()
            if not selected:
                messagebox.showinfo(APP_NAME, "Select one or more rules in the Scope tab before clicking Remove selected.")
                return
            indexes = {int(item) for item in selected}
            paths = workflow.source_paths(self.repo_root, key, "rules")
            rules = workflow.load_scope_rules(paths.scope_dir)
            kept = [rule for index, rule in enumerate(rules) if index not in indexes]
            workflow.write_tsv(paths.scope_dir / "scope_rules.tsv", kept, workflow.SCOPE_RULE_FIELDS)
            self.append_log(f"Removed {len(indexes)} scope rule(s) for {key}.")
            self.load_scope_rules_view()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not remove the selected rule.\n\nWhat happened: {exc}\n\nWhat to do: reload rules and try again.")

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
                    result = message.get("result", {})
                    self.current_step_var.set(self._completion_text(result))
                    self.counter_var.set(self._counter_text(result))
                    self.append_log(json.dumps(result, indent=2))
                    self.show_user_result_summary(result)
                    self.profiles = workflow.load_public_profiles(self.repo_root)
                    self.show_dataset_status()
                else:
                    self.progress.configure(value=0)
                    self.current_step_var.set("Error")
                    self.append_log(message.get("error", "Unknown error"))
                    self.append_log(message.get("traceback", ""))
                    messagebox.showerror(APP_NAME, f"The task failed before it could finish.\n\nWhat happened: {message.get('error', 'Unknown error')}\n\nWhat to do: check that the selected source has the required fields filled, then try again. The detailed traceback is in the log panel.")
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

    def _completion_text(self, result: dict[str, Any]) -> str:
        if "manifest_rows" in result:
            failed = [row for row in result["manifest_rows"] if row.get("status") == "error"]
            skipped = [row for row in result["manifest_rows"] if row.get("status") == "skipped"]
            if failed:
                return f"Completed with errors: {len(failed)} failed, {len(result['manifest_rows']) - len(failed) - len(skipped)} ok"
            if skipped:
                return f"Complete with skipped files: {len(skipped)} skipped"
        if "errors" in result and result.get("errors"):
            return "Validation failed"
        if "warnings" in result and result.get("warnings"):
            return "Validation complete with warnings"
        return "Complete"

    def show_user_result_summary(self, result: dict[str, Any]) -> None:
        if "manifest_rows" in result:
            failed = [row for row in result["manifest_rows"] if row.get("status") == "error"]
            skipped = [row for row in result["manifest_rows"] if row.get("status") == "skipped"]
            if not failed and not skipped:
                return
            lines = []
            if failed:
                lines.append("Some provider files did not download.")
                for row in failed[:6]:
                    label = row.get("file_label", "file")
                    error = row.get("error", "")
                    if "HTTP Error 884" in error:
                        lines.append(f"- {label}: the provider refused this endpoint (HTTP 884). The trial may not allow M3U playlist export, or the provider may require a different portal/output setting.")
                    else:
                        lines.append(f"- {label}: {error}")
            if skipped:
                lines.append("Some files were skipped because required URLs were not configured.")
                for row in skipped[:6]:
                    label = row.get("file_label", "file")
                    if row.get("error") == "url_not_configured":
                        lines.append(f"- {label}: no URL is configured. For Xtream Codes, use server URL + username + password instead of a standalone M3U URL.")
                    else:
                        lines.append(f"- {label}: {row.get('error', '')}")
            lines.append("")
            lines.append("Next: use Fetch Xtream API metadata or Fetch all for this provider, then open Reports to review groups, live TV, movies, and shows from the API baseline.")
            messagebox.showwarning(APP_NAME, "\n".join(lines))
        elif "all_stream_records" in result:
            messagebox.showinfo(
                APP_NAME,
                f"Parse/export finished.\n\nStreams: {result.get('all_stream_records', 0):,}\nLive TV: {result.get('live_tv_channels', 0):,}\nMovies: {result.get('vod_movies', 0):,}\nShows: {result.get('series', 0):,}\nEPG channels: {result.get('epg_channels', 0):,}\n\nOpen the Reports tab to review groups and categories.",
            )

    def latest_report_dir(self) -> Path:
        return workflow.source_paths(self.repo_root, self.selected_source_key(), "report").latest_report

    def read_latest_tsv(self, file_name: str) -> list[dict[str, str]]:
        path = self.latest_report_dir() / file_name
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]

    def clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def set_report_columns(self, columns: list[str]) -> None:
        self.report_tree.configure(columns=columns)
        for column in columns:
            self.report_tree.heading(column, text=column)
            width = 120
            if column in {"title", "raw_title", "group_title", "xtream_category_name"}:
                width = 260
            if column in {"count", "record_count"}:
                width = 90
            self.report_tree.column(column, width=width, anchor="w")

    def load_report_view(self, report_type: str) -> None:
        try:
            if report_type == "groups":
                rows = self.read_latest_tsv("m3u_group_summary.tsv")
                columns = ["item_type", "group_title", "record_count"]
                display_rows = rows
            elif report_type == "live":
                rows = self.read_latest_tsv("live_tv_channels.tsv")
                columns = ["raw_title", "xtream_category_name", "group_title", "country_normalized", "language_normalized", "network_normalized"]
                display_rows = rows[:5000]
            elif report_type == "movies":
                rows = self.read_latest_tsv("vod_movies.tsv")
                columns = ["raw_title", "xtream_category_name", "group_title", "country_normalized", "language_normalized"]
                display_rows = rows[:5000]
            else:
                rows = self.read_latest_tsv("series.tsv")
                columns = ["raw_title", "xtream_category_name", "group_title", "country_normalized", "language_normalized"]
                display_rows = rows[:5000]
            self.clear_tree(self.report_tree)
            self.set_report_columns(columns)
            for index, row in enumerate(display_rows):
                self.report_tree.insert("", "end", iid=str(index), values=[row.get(column, "") for column in columns])
            self.append_log(f"Loaded report view '{report_type}' with {len(display_rows):,} displayed row(s).")
        except FileNotFoundError as exc:
            messagebox.showinfo(
                APP_NAME,
                f"Report TSVs are not available yet.\n\nWhat happened: {exc}\n\nWhat to do: fetch provider data, click Parse selected, then return to the Reports tab.",
            )
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not load the report view.\n\nWhat happened: {exc}\n\nWhat to do: run Parse selected again and verify the latest report folder exists.")


def main() -> int:
    app = MultiSourceGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
