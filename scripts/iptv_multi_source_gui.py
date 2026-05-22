from __future__ import annotations

import csv
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
APP_VERSION = "1.1.0"

UI_FIELDS = {
    "group_title": "Group",
    "raw_title": "Original Title",
    "normalized_title": "Title",
    "country_normalized": "Country",
    "language_normalized": "Language",
    "network_normalized": "Network",
    "item_type": "Content Type",
    "tvg_id": "TV Guide ID",
    "tvg_name": "TV Guide Name",
    "tvg_logo": "Logo",
    "stream_host": "Stream Host",
    "stream_extension": "Stream Format",
    "include_candidate": "Include?",
    "exclude_candidate": "Exclude?",
    "xtream_category_name": "Category",
}
FIELD_BY_LABEL = {label: field for field, label in UI_FIELDS.items()}
CONTENT_TYPE_LABELS = {
    "live_tv": "Live TV",
    "vod_movie": "Movie",
    "series": "Series",
    "series_episode": "Series Episode",
    "catchup": "Catch-up",
    "unknown": "Unknown",
}
CONTENT_TYPE_BY_LABEL = {label: key for key, label in CONTENT_TYPE_LABELS.items()}
SOURCE_TYPE_LABELS = {"direct_urls": "Direct Playlist URLs", "xtream_codes": "Xtream Codes Login"}
SOURCE_TYPE_BY_LABEL = {label: key for key, label in SOURCE_TYPE_LABELS.items()}


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event: tk.Event | None = None) -> None:
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + 24
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.window, text=self.text, justify="left", background="#fff8d6", relief="solid", borderwidth=1, padx=8, pady=4)
        label.pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.window:
            self.window.destroy()
            self.window = None


class MultiSourceGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.repo_root = REPO_ROOT
        workflow.ensure_base_files(self.repo_root)
        self.worker_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.profiles = workflow.load_public_profiles(self.repo_root)
        self.selected_key = ""
        self.value_list_data: list[dict[str, Any]] = []
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1500x980")
        self.minsize(1220, 780)
        self._build_variables()
        self._build_styles()
        self._build_menu()
        self._build_layout()
        self.refresh_sources()
        self.after(100, self._poll_worker_queue)

    def _build_variables(self) -> None:
        self.show_archived_var = tk.BooleanVar(value=False)
        self.source_display_name_var = tk.StringVar()
        self.source_key_var = tk.StringVar()
        self.source_type_var = tk.StringVar(value=SOURCE_TYPE_LABELS["direct_urls"])
        self.provider_label_var = tk.StringVar()
        self.server_url_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.password_visible_var = tk.BooleanVar(value=False)
        self.m3u_url_var = tk.StringVar()
        self.epg_url_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.paste_url_var = tk.StringVar()
        self.safe_urls_var = tk.StringVar(value="No source selected")
        self.source_status_var = tk.StringVar(value="Choose or create a source")
        self.current_action_var = tk.StringVar(value="Ready")
        self.next_action_var = tk.StringVar(value="Next: paste a provider URL or choose a saved source.")
        self.counter_var = tk.StringVar(value="")
        self.rule_action_var = tk.StringVar(value="include")
        self.rule_field_label_var = tk.StringVar(value="Group")
        self.rule_operator_var = tk.StringVar(value="equals")
        self.rule_search_var = tk.StringVar()
        self.rule_preview_var = tk.StringVar(value="Select values to preview affected records.")
        self.parse_m3u_var = tk.BooleanVar(value=True)
        self.parse_epg_var = tk.BooleanVar(value=True)
        self.parse_xtream_var = tk.BooleanVar(value=True)
        self.export_feeds_var = tk.BooleanVar(value=True)

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10))
        style.configure("Step.TFrame", relief="solid", borderwidth=1)
        style.configure("Card.TFrame", relief="solid", borderwidth=1)
        style.configure("Danger.TButton", foreground="#8a1f11")

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        self.config(menu=menu)

        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New Source", command=self.new_source)
        file_menu.add_command(label="Open Source Folder", command=self.open_source_data_folder)
        file_menu.add_command(label="Open Latest Report Folder", command=self.open_latest_report_folder)
        file_menu.add_command(label="Export TSV Package", command=self.export_tsv_package)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="Edit Source", command=self.focus_source_editor)
        edit_menu.add_command(label="Duplicate Source", command=self.duplicate_source)
        edit_menu.add_command(label="Archive Source", command=self.archive_source)
        edit_menu.add_command(label="Delete Source", command=self.delete_source)
        menu.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Source Dashboard", command=lambda: self.main_notebook.select(self.dashboard_tab))
        view_menu.add_command(label="Inventory Preview", command=lambda: self.main_notebook.select(self.inventory_tab))
        view_menu.add_command(label="Reports", command=lambda: self.main_notebook.select(self.reports_tab))
        view_menu.add_command(label="Logs", command=lambda: self.main_notebook.select(self.logs_tab))
        menu.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="Test Source", command=self.test_source)
        tools_menu.add_command(label="Fetch Data", command=lambda: self.start_fetch(True, True, True))
        tools_menu.add_command(label="Parse Inventory", command=self.start_parse)
        tools_menu.add_command(label="Run Full Inventory", command=self.run_full_inventory)
        tools_menu.add_command(label="Validate Source", command=self.validate_selected_source)
        tools_menu.add_command(label="Validate Reports", command=self.validate_reports)
        menu.add_cascade(label="Tools", menu=tools_menu)

        configure_menu = tk.Menu(menu, tearoff=False)
        configure_menu.add_command(label="Source Profiles", command=lambda: self.open_path(self.repo_root / "data" / "source_profiles"))
        configure_menu.add_command(label="Private Credentials", command=lambda: self.open_path(self.repo_root / "data" / "source_profiles"))
        configure_menu.add_command(label="Network Reference Data", command=self.open_reference_locations)
        configure_menu.add_command(label="Export Settings", command=self.focus_export_settings)
        menu.add_cascade(label="Configure", menu=configure_menu)

        window_menu = tk.Menu(menu, tearoff=False)
        window_menu.add_command(label="Reset Layout", command=self.reset_layout)
        window_menu.add_command(label="Open Logs", command=lambda: self.open_path(self.repo_root / "logs"))
        menu.add_cascade(label="Window", menu=window_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Workflow Guide", command=self.open_workflow_guide)
        help_menu.add_command(label="Field Dictionary", command=self.show_field_dictionary)
        help_menu.add_command(label="Troubleshooting", command=self.show_troubleshooting)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_toolbar()
        body = ttk.PanedWindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")
        self.left_panel = ttk.Frame(body, width=330)
        self.center_panel = ttk.Frame(body)
        self.right_panel = ttk.Frame(body, width=300)
        body.add(self.left_panel, weight=0)
        body.add(self.center_panel, weight=1)
        body.add(self.right_panel, weight=0)
        self._build_source_list(self.left_panel)
        self._build_center(self.center_panel)
        self._build_summary_panel(self.right_panel)
        self._build_progress()

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(5, weight=1)
        ttk.Label(toolbar, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, padx=(0, 14), sticky="w")
        self.make_button(toolbar, "New Source", self.new_source, "Start a new provider profile.").grid(row=0, column=1, padx=4)
        self.make_button(toolbar, "Analyze URL", self.analyze_pasted_url, "Read a pasted playlist, TV guide, or Xtream API URL and fill the source fields.").grid(row=0, column=2, padx=4)
        self.make_button(toolbar, "Save Source", self.save_source, "Save public profile details and local private credentials.").grid(row=0, column=3, padx=4)
        run = ttk.Button(toolbar, text="Run Full Inventory", style="Primary.TButton", command=self.run_full_inventory)
        run.grid(row=0, column=4, padx=10)
        ToolTip(run, "Validate, fetch, parse, export reports, export source feeds, and validate the result.")
        self.status_badge = tk.Label(toolbar, text="No source", bg="#6b7280", fg="white", padx=10, pady=4)
        self.status_badge.grid(row=0, column=6, padx=8, sticky="e")

    def _build_source_list(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Sources", style="Section.TLabel").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        ttk.Checkbutton(parent, text="Show archived sources", variable=self.show_archived_var, command=self.refresh_sources).grid(row=1, column=0, padx=10, pady=4, sticky="w")
        self.source_cards = ttk.Frame(parent)
        self.source_cards.grid(row=2, column=0, padx=10, pady=4, sticky="new")
        parent.rowconfigure(3, weight=1)

    def _build_center(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.main_notebook = ttk.Notebook(parent)
        self.main_notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.dashboard_tab = ttk.Frame(self.main_notebook)
        self.inventory_tab = ttk.Frame(self.main_notebook)
        self.reports_tab = ttk.Frame(self.main_notebook)
        self.logs_tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.dashboard_tab, text="Source Dashboard")
        self.main_notebook.add(self.inventory_tab, text="Inventory Preview")
        self.main_notebook.add(self.reports_tab, text="Reports and Filters")
        self.main_notebook.add(self.logs_tab, text="Logs")
        self._build_dashboard_tab()
        self._build_inventory_tab()
        self._build_reports_tab()
        self._build_logs_tab()

    def _build_dashboard_tab(self) -> None:
        self.dashboard_tab.columnconfigure(0, weight=1)
        self._build_workflow_steps(self.dashboard_tab)
        self._build_source_input(self.dashboard_tab)
        self._build_source_editor(self.dashboard_tab)
        self._build_advanced_actions(self.dashboard_tab)

    def _build_workflow_steps(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Workflow")
        frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for index, (title, helper) in enumerate(
            [
                ("1 Source", "Paste URL or choose saved source"),
                ("2 Fetch", "Download playlist, guide, and metadata"),
                ("3 Parse", "Build channels, movies, shows, and guide records"),
                ("4 Review", "Inspect groups, categories, and filters"),
                ("5 Export / Publish", "Write source-specific playlist and guide"),
            ]
        ):
            card = ttk.Frame(frame, style="Step.TFrame", padding=8)
            card.grid(row=0, column=index, padx=5, pady=8, sticky="nsew")
            ttk.Label(card, text=title, style="Section.TLabel").pack(anchor="w")
            ttk.Label(card, text=helper, wraplength=150).pack(anchor="w")
        for index in range(5):
            frame.columnconfigure(index, weight=1)

    def _build_source_input(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Step 1 - Paste Playlist URL or Xtream Details")
        frame.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Paste a playlist, TV guide, or Xtream API URL. The app will fill server, username, password, playlist, TV guide, and API URLs when they are present.").grid(row=0, column=0, columnspan=5, padx=8, pady=(8, 4), sticky="w")
        ttk.Entry(frame, textvariable=self.paste_url_var).grid(row=1, column=0, padx=8, pady=8, sticky="ew")
        self.make_button(frame, "Analyze URL", self.analyze_pasted_url, "Extract source details from the pasted URL.").grid(row=1, column=1, padx=4)
        self.make_button(frame, "View Safe URLs", self.view_safe_urls, "Show playlist and guide URLs with username and password hidden.").grid(row=1, column=2, padx=4)
        self.make_button(frame, "Copy Safe URLs", self.copy_safe_urls, "Copy redacted URLs for notes or documentation.").grid(row=1, column=3, padx=4)
        self.make_button(frame, "Copy Private Local URLs", self.copy_private_urls, "Copy full local URLs with credentials. Use only on this machine.").grid(row=1, column=4, padx=4)
        ttk.Label(frame, textvariable=self.safe_urls_var, wraplength=900).grid(row=2, column=0, columnspan=5, padx=8, pady=(0, 8), sticky="w")

    def _build_source_editor(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Source Setup")
        frame.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        for column in range(4):
            frame.columnconfigure(column, weight=1)
        labels = [
            ("Source Name", self.source_display_name_var),
            ("Source ID", self.source_key_var),
            ("Provider Label", self.provider_label_var),
            ("Server", self.server_url_var),
            ("Username", self.username_var),
            ("Playlist URL", self.m3u_url_var),
            ("TV Guide URL", self.epg_url_var),
        ]
        for index, (label, variable) in enumerate(labels):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(frame, text=label).grid(row=row, column=col, padx=8, pady=5, sticky="w")
            ttk.Entry(frame, textvariable=variable).grid(row=row, column=col + 1, padx=8, pady=5, sticky="ew")
        ttk.Label(frame, text="Source Type").grid(row=3, column=2, padx=8, pady=5, sticky="w")
        ttk.Combobox(frame, textvariable=self.source_type_var, state="readonly", values=list(SOURCE_TYPE_BY_LABEL)).grid(row=3, column=3, padx=8, pady=5, sticky="ew")
        ttk.Label(frame, text="Password").grid(row=4, column=0, padx=8, pady=5, sticky="w")
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=4, column=1, padx=8, pady=5, sticky="ew")
        self.make_button(frame, "Show / Hide", self.toggle_password, "Show or hide the local password field.").grid(row=4, column=2, padx=8, pady=5, sticky="w")
        self.make_button(frame, "Copy Username", lambda: self.copy_text(self.username_var.get()), "Copy username to the clipboard.").grid(row=5, column=0, padx=8, pady=5, sticky="w")
        self.make_button(frame, "Copy Password", lambda: self.copy_text(self.password_var.get()), "Copy password to the clipboard without logging it.").grid(row=5, column=1, padx=8, pady=5, sticky="w")
        ttk.Label(frame, text="Notes").grid(row=5, column=2, padx=8, pady=5, sticky="w")
        ttk.Entry(frame, textvariable=self.notes_var).grid(row=5, column=3, padx=8, pady=5, sticky="ew")

    def _build_advanced_actions(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Advanced Actions")
        frame.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
        actions = [
            ("Fetch All Source Data", lambda: self.start_fetch(True, True, True), "Download playlist, TV guide, and Xtream metadata."),
            ("Fetch Channel/Movie/Series Metadata", lambda: self.start_fetch(False, False, True), "Download Xtream category, channel, movie, and series metadata."),
            ("Parse Inventory", self.start_parse, "Generate TSV reports and source-specific feed outputs."),
            ("View Source Status", self.view_source_status, "Show whether local playlist, guide, metadata, reports, and feeds exist."),
            ("Open Source Data Folder", self.open_source_data_folder, "Open the source-specific filtered feed folder."),
            ("Open Source Filters Folder", self.open_source_filters_folder, "Open the source-specific filter rules folder."),
        ]
        for index, (label, command, tip) in enumerate(actions):
            self.make_button(frame, label, command, tip).grid(row=index // 3, column=index % 3, padx=8, pady=6, sticky="ew")
            frame.columnconfigure(index % 3, weight=1)

    def _build_inventory_tab(self) -> None:
        self.inventory_tab.columnconfigure(0, weight=1)
        self.inventory_tab.rowconfigure(1, weight=1)
        controls = ttk.Frame(self.inventory_tab)
        controls.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for index, (label, report_type) in enumerate([("Groups / Categories", "groups"), ("Live TV Channels", "live"), ("Movies", "movies"), ("Shows / Series", "series"), ("TV Guide Channels", "epg_channels"), ("TV Guide Programmes", "epg_programmes")]):
            self.make_button(controls, label, lambda kind=report_type: self.load_report_view(kind), f"Load {label.lower()} from the latest TSV reports.").grid(row=0, column=index, padx=4)
        self.report_tree = ttk.Treeview(self.inventory_tab, show="headings")
        self.report_tree.grid(row=1, column=0, padx=(8, 0), pady=8, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.inventory_tab, orient="vertical", command=self.report_tree.yview)
        scrollbar.grid(row=1, column=1, padx=(0, 8), pady=8, sticky="ns")
        self.report_tree.configure(yscrollcommand=scrollbar.set)

    def _build_reports_tab(self) -> None:
        self.reports_tab.columnconfigure(0, weight=1)
        self.reports_tab.rowconfigure(2, weight=1)
        filter_frame = ttk.LabelFrame(self.reports_tab, text="Build Source Filters from Actual Values")
        filter_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for col in range(8):
            filter_frame.columnconfigure(col, weight=1 if col in {1, 3} else 0)
        ttk.Label(filter_frame, text="Action").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        ttk.Combobox(filter_frame, textvariable=self.rule_action_var, state="readonly", values=["include", "exclude"], width=10).grid(row=0, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(filter_frame, text="Field").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        field_box = ttk.Combobox(filter_frame, textvariable=self.rule_field_label_var, state="readonly", values=sorted(FIELD_BY_LABEL), width=24)
        field_box.grid(row=0, column=3, padx=6, pady=4, sticky="w")
        field_box.bind("<<ComboboxSelected>>", lambda _event: self.load_filter_values())
        ttk.Label(filter_frame, text="Match").grid(row=0, column=4, padx=6, pady=4, sticky="w")
        ttk.Combobox(filter_frame, textvariable=self.rule_operator_var, state="readonly", values=["equals", "contains", "starts_with", "ends_with", "regex", "in_list", "not_equals"], width=16).grid(row=0, column=5, padx=6, pady=4, sticky="w")
        ttk.Label(filter_frame, text="Search Values").grid(row=1, column=0, padx=6, pady=4, sticky="w")
        search_entry = ttk.Entry(filter_frame, textvariable=self.rule_search_var)
        search_entry.grid(row=1, column=1, columnspan=3, padx=6, pady=4, sticky="ew")
        search_entry.bind("<KeyRelease>", lambda _event: self.load_filter_values())
        self.make_button(filter_frame, "Preview Affected Records", self.preview_scope_count, "Count records matching the selected field values.").grid(row=1, column=4, padx=6, pady=4)
        self.make_button(filter_frame, "Add Filter Rule", self.save_scope_rule, "Save the selected include/exclude rule for this source.").grid(row=1, column=5, padx=6, pady=4)
        self.make_button(filter_frame, "Clear Filters", self.clear_scope_rules, "Remove saved filter rules for this source.").grid(row=1, column=6, padx=6, pady=4)
        self.make_button(filter_frame, "Apply and Export", self.start_parse, "Reparse with saved filter rules and export source-specific playlist and TV guide.").grid(row=1, column=7, padx=6, pady=4)

        values_frame = ttk.Frame(self.reports_tab)
        values_frame.grid(row=1, column=0, sticky="ew", padx=8)
        values_frame.columnconfigure(0, weight=1)
        ttk.Label(values_frame, text="Values from latest parsed data. Use Ctrl/Shift to select multiple values.").grid(row=0, column=0, sticky="w")
        ttk.Label(values_frame, textvariable=self.rule_preview_var).grid(row=0, column=1, sticky="e")
        self.value_listbox = tk.Listbox(values_frame, selectmode="extended", height=8, exportselection=False)
        self.value_listbox.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)

        columns = ("Action", "Field", "Match", "Value", "Enabled", "Notes")
        self.scope_rules_tree = ttk.Treeview(self.reports_tab, columns=columns, show="headings", height=8)
        for column in columns:
            self.scope_rules_tree.heading(column, text=column)
            self.scope_rules_tree.column(column, width=160 if column != "Value" else 320, anchor="w")
        self.scope_rules_tree.grid(row=2, column=0, padx=8, pady=8, sticky="nsew")
        self.make_button(self.reports_tab, "Remove Selected Rule", self.remove_selected_scope_rule, "Remove highlighted filter rules from this source.").grid(row=3, column=0, padx=8, pady=(0, 8), sticky="w")

    def _build_logs_tab(self) -> None:
        self.logs_tab.columnconfigure(0, weight=1)
        self.logs_tab.rowconfigure(0, weight=1)
        self.log_text = tk.Text(self.logs_tab, wrap="word", height=16)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar = ttk.Scrollbar(self.logs_tab, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.append_log(f"{APP_NAME} {APP_VERSION}")
        self.append_log(f"Repo root: {self.repo_root}")

    def _build_summary_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Current Source", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        self.summary_text = tk.Text(parent, height=26, wrap="word", state="disabled", bg="#f9fafb", relief="solid", borderwidth=1)
        self.summary_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        parent.rowconfigure(1, weight=1)

    def _build_progress(self) -> None:
        frame = ttk.Frame(self, padding=(10, 6))
        frame.grid(row=2, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, textvariable=self.current_action_var).grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=1, sticky="ew")
        ttk.Label(frame, textvariable=self.counter_var).grid(row=0, column=2, padx=8, sticky="e")
        ttk.Label(frame, textvariable=self.next_action_var).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def make_button(self, parent: tk.Widget, label: str, command: Any, tooltip: str) -> ttk.Button:
        button = ttk.Button(parent, text=label, command=command)
        ToolTip(button, tooltip)
        return button

    def append_log(self, text: str) -> None:
        safe = workflow.redact_url(text)
        self.log_text.insert("end", f"{workflow.utc_iso()}  {safe}\n")
        self.log_text.see("end")

    def refresh_sources(self) -> None:
        self.profiles = workflow.load_public_profiles(self.repo_root)
        for child in self.source_cards.winfo_children():
            child.destroy()
        visible = [(key, profile) for key, profile in sorted(self.profiles.items()) if self.show_archived_var.get() or profile.get("source_status") != "archived"]
        if not visible:
            ttk.Label(self.source_cards, text="No active sources. Click New Source or paste a provider URL.").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        for row, (key, profile) in enumerate(visible):
            self.add_source_card(row, key, profile)
        if not self.selected_key or self.selected_key not in dict(visible):
            active = next((key for key, profile in sorted(self.profiles.items()) if profile.get("source_status") != "archived"), "")
            self.selected_key = active or (visible[0][0] if visible else "")
            if self.selected_key:
                self.load_source(self.selected_key)

    def add_source_card(self, row: int, key: str, profile: dict[str, Any]) -> None:
        counts = workflow.latest_report_counts(self.repo_root, key)
        status = profile.get("source_status", "configured")
        bg = "#f3f4f6" if status == "archived" else "#ffffff"
        card = tk.Frame(self.source_cards, bg=bg, relief="solid", borderwidth=1, padx=8, pady=8)
        card.grid(row=row, column=0, sticky="ew", pady=5)
        card.columnconfigure(0, weight=1)
        tk.Label(card, text=profile.get("source_display_name", key), bg=bg, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(card, text=f"ID: {key}", bg=bg).grid(row=1, column=0, sticky="w")
        tk.Label(card, text=f"Status: {self.status_label(status)}", bg=bg).grid(row=2, column=0, sticky="w")
        tk.Label(card, text=f"Live {counts['live_tv']:,} | Movies {counts['movies']:,} | Shows {counts['series']:,}", bg=bg).grid(row=3, column=0, sticky="w")
        buttons = ttk.Frame(card)
        buttons.grid(row=4, column=0, pady=(6, 0), sticky="ew")
        self.make_button(buttons, "Use Source", lambda source=key: self.load_source(source), "Select this source for fetch, parse, review, and export.").grid(row=0, column=0, padx=2)
        self.make_button(buttons, "Edit", lambda source=key: self.load_source(source), "Load this source into the editor.").grid(row=0, column=1, padx=2)
        self.make_button(buttons, "Run Full Inventory", lambda source=key: self.run_full_inventory(source), "Run the full workflow for this source.").grid(row=0, column=2, padx=2)
        self.make_button(buttons, "Open Reports", lambda source=key: self.open_latest_report_folder(source), "Open latest TSV report folder.").grid(row=1, column=0, padx=2, pady=2)
        self.make_button(buttons, "Archive", lambda source=key: self.archive_source(source), "Archive this source profile without deleting local data.").grid(row=1, column=1, padx=2, pady=2)

    def status_label(self, status: str) -> str:
        return {"parsed": "Active", "fetched": "Active", "partial_fetch": "Warning", "fetch_error": "Error", "configured": "Needs Setup", "archived": "Archived"}.get(status, status or "Needs Setup")

    def update_status_badge(self, status: str) -> None:
        label = self.status_label(status)
        color = {"Active": "#137333", "Warning": "#b45309", "Error": "#b91c1c", "Archived": "#6b7280", "Needs Setup": "#374151"}.get(label, "#374151")
        self.status_badge.configure(text=label, bg=color)

    def load_source(self, source_key: str) -> None:
        key = workflow.clean_source_key(source_key)
        profile = self.profiles.get(key, {})
        private = workflow.load_private_profiles(self.repo_root).get(key, {})
        self.selected_key = key
        self.source_display_name_var.set(profile.get("source_display_name", ""))
        self.source_key_var.set(key)
        self.source_type_var.set(SOURCE_TYPE_LABELS.get(profile.get("source_type", "direct_urls"), SOURCE_TYPE_LABELS["direct_urls"]))
        self.provider_label_var.set(profile.get("provider_label", ""))
        self.server_url_var.set(private.get("server_url", ""))
        self.username_var.set(private.get("username", ""))
        self.password_var.set(private.get("password", ""))
        self.m3u_url_var.set(private.get("m3u_url", ""))
        self.epg_url_var.set(private.get("epg_url", ""))
        self.notes_var.set(profile.get("notes", ""))
        self.show_safe_urls_inline()
        self.update_summary()
        self.update_status_badge(profile.get("source_status", "configured"))
        self.load_scope_rules_view()
        self.load_filter_values()
        self.next_action_var.set("Next: run full inventory, or review reports if the source was already parsed.")

    def selected_source_type(self) -> str:
        return SOURCE_TYPE_BY_LABEL.get(self.source_type_var.get(), self.source_type_var.get() or "direct_urls")

    def selected_source_key(self) -> str:
        key = self.source_key_var.get().strip() or self.selected_key
        return workflow.clean_source_key(key)

    def new_source(self) -> None:
        self.selected_key = ""
        for variable in [self.source_display_name_var, self.source_key_var, self.provider_label_var, self.server_url_var, self.username_var, self.password_var, self.m3u_url_var, self.epg_url_var, self.notes_var, self.paste_url_var]:
            variable.set("")
        self.source_type_var.set(SOURCE_TYPE_LABELS["direct_urls"])
        self.safe_urls_var.set("Paste a playlist or Xtream URL, then click Analyze URL.")
        self.source_status_var.set("New source")
        self.update_status_badge("configured")
        self.update_summary()
        self.next_action_var.set("Next: paste the provider URL and click Analyze URL.")
        self.main_notebook.select(self.dashboard_tab)

    def analyze_pasted_url(self) -> dict[str, str] | None:
        try:
            url = self.paste_url_var.get().strip() or self.m3u_url_var.get().strip() or self.epg_url_var.get().strip()
            analysis = workflow.analyze_source_url(url)
            self.source_display_name_var.set(analysis["source_display_name"])
            self.source_key_var.set(analysis["source_key"])
            self.source_type_var.set(SOURCE_TYPE_LABELS.get(analysis["source_type"], SOURCE_TYPE_LABELS["direct_urls"]))
            self.provider_label_var.set(analysis["provider_label"])
            self.server_url_var.set(analysis["server_url"])
            self.username_var.set(analysis["username"])
            self.password_var.set(analysis["password"])
            self.m3u_url_var.set(analysis["m3u_url"])
            self.epg_url_var.set(analysis["epg_url"])
            self.show_safe_urls_inline()
            self.append_log(f"Analyzed provider URL for source candidate {analysis['source_key']} with redacted values only.")
            self.next_action_var.set("Next: verify Source Name and Source ID, then click Save Source.")
            return analysis
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The URL could not be analyzed.\n\nWhat happened: {exc}\n\nWhat to do: paste the full provider playlist, TV guide, or Xtream API URL and try Analyze URL again.")
            return None

    def save_source(self) -> dict[str, Any] | None:
        try:
            if self.paste_url_var.get().strip() and not self.source_key_var.get().strip():
                self.analyze_pasted_url()
            if not self.source_key_var.get().strip() and self.source_display_name_var.get().strip():
                self.source_key_var.set(workflow.clean_source_key(self.source_display_name_var.get()))
            public = {
                "source_key": self.source_key_var.get(),
                "source_display_name": self.source_display_name_var.get(),
                "source_type": self.selected_source_type(),
                "provider_label": self.provider_label_var.get(),
                "notes": self.notes_var.get(),
                "source_status": "configured",
            }
            private = {
                "source_key": self.source_key_var.get(),
                "source_type": self.selected_source_type(),
                "server_url": self.server_url_var.get().strip(),
                "username": self.username_var.get().strip(),
                "password": self.password_var.get(),
                "m3u_url": self.m3u_url_var.get().strip(),
                "epg_url": self.epg_url_var.get().strip(),
            }
            profile = workflow.upsert_source_profile(self.repo_root, public, private)
            self.selected_key = profile["source_key"]
            self.refresh_sources()
            self.load_source(profile["source_key"])
            self.append_log(f"Saved source profile: {profile['source_key']}")
            self.next_action_var.set("Next: click Run Full Inventory to fetch, parse, export, and validate.")
            return profile
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The source could not be saved.\n\nWhat happened: {exc}\n\nWhat to do: make sure Source Name and Source ID are filled, and Xtream sources have Server, Username, and Password.")
            self.append_log(f"Save failed: {exc}")
            return None

    def duplicate_source(self) -> None:
        try:
            key = self.selected_source_key()
            profile = workflow.duplicate_source_profile(self.repo_root, key)
            self.refresh_sources()
            self.load_source(profile["source_key"])
            self.append_log(f"Duplicated source profile: {key} -> {profile['source_key']}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The source could not be duplicated.\n\nWhat happened: {exc}")

    def archive_source(self, source_key: str | None = None) -> None:
        try:
            key = workflow.clean_source_key(source_key or self.selected_source_key())
            if not messagebox.askyesno(APP_NAME, f"Archive source '{key}'?\n\nFetched data and reports stay on disk."):
                return
            workflow.archive_source_profile(self.repo_root, key)
            self.append_log(f"Archived source profile: {key}")
            self.refresh_sources()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The source could not be archived.\n\nWhat happened: {exc}")

    def delete_source(self) -> None:
        try:
            key = self.selected_source_key()
            if not messagebox.askyesno(APP_NAME, f"Delete source profile '{key}'?\n\nOnly the profile and private credentials are removed. Captured datasets and reports are preserved."):
                return
            result = workflow.delete_source_profile(self.repo_root, key, delete_private=True)
            self.append_log(f"Deleted source profile: {json.dumps(result)}")
            self.new_source()
            self.refresh_sources()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The source could not be deleted.\n\nWhat happened: {exc}")

    def show_safe_urls_inline(self) -> None:
        try:
            urls = self.current_urls()
            self.safe_urls_var.set(f"Safe playlist: {workflow.redact_url(urls.get('m3u_url', ''))} | Safe TV guide: {workflow.redact_url(urls.get('epg_url', ''))} | Safe API: {workflow.redact_url(urls.get('api_base', ''))}")
        except Exception as exc:
            self.safe_urls_var.set(f"Safe URL view could not be built: {exc}")

    def current_urls(self) -> dict[str, str]:
        if self.selected_source_type() == "xtream_codes":
            return workflow.derive_xtream_urls(self.server_url_var.get(), self.username_var.get(), self.password_var.get())
        return {"m3u_url": self.m3u_url_var.get(), "epg_url": self.epg_url_var.get(), "api_base": ""}

    def view_safe_urls(self) -> None:
        self.show_safe_urls_inline()
        messagebox.showinfo(APP_NAME, self.safe_urls_var.get())

    def copy_safe_urls(self) -> None:
        self.show_safe_urls_inline()
        self.copy_text(self.safe_urls_var.get())

    def copy_private_urls(self) -> None:
        urls = self.current_urls()
        text = f"Playlist URL: {urls.get('m3u_url', '')}\nTV Guide URL: {urls.get('epg_url', '')}\nXtream API URL: {urls.get('api_base', '')}"
        self.copy_text(text)
        messagebox.showwarning(APP_NAME, "Private local URLs were copied to the clipboard.\n\nThey include credentials. Do not paste them into committed files, tickets, chat, or public reports.")

    def copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def toggle_password(self) -> None:
        self.password_visible_var.set(not self.password_visible_var.get())
        self.password_entry.configure(show="" if self.password_visible_var.get() else "*")

    def test_source(self) -> None:
        if self.save_source() is None:
            return
        try:
            urls = workflow.resolve_source_urls(self.repo_root, self.selected_source_key())
            missing = []
            if self.selected_source_type() == "xtream_codes":
                if not urls.get("m3u_url"):
                    missing.append("playlist")
                if not urls.get("epg_url"):
                    missing.append("TV guide")
                if not urls.get("api_base"):
                    missing.append("metadata API")
            elif not urls.get("m3u_url"):
                missing.append("playlist")
            if missing:
                raise ValueError("Missing " + ", ".join(missing))
            messagebox.showinfo(APP_NAME, "Source setup looks complete. URLs are valid enough to fetch, and credentials remain local/private.")
            self.append_log("Source URL test passed with redacted values only.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Source setup needs attention.\n\nWhat happened: {exc}\n\nWhat to do: use Analyze URL or fill Server, Username, Password, Playlist URL, and TV Guide URL as needed.")

    def start_fetch(self, fetch_m3u: bool, fetch_epg: bool, fetch_xtream: bool) -> None:
        if self.save_source() is None:
            return
        self._start_worker("Fetching source data...", workflow.fetch_source, self.repo_root, self.selected_source_key(), fetch_m3u, fetch_epg, fetch_xtream)

    def start_parse(self) -> None:
        try:
            key = self.selected_source_key()
        except Exception:
            messagebox.showinfo(APP_NAME, "Choose or save a source before parsing.")
            return
        self._start_worker("Parsing inventory and exporting reports...", workflow.parse_source, self.repo_root, key, True, self.export_feeds_var.get(), self.parse_m3u_var.get(), self.parse_epg_var.get(), self.parse_xtream_var.get())

    def run_full_inventory(self, source_key: str | None = None) -> None:
        if source_key:
            self.load_source(source_key)
        if self.save_source() is None:
            return
        self._start_worker("Running full inventory workflow...", workflow.run_full_inventory, self.repo_root, self.selected_source_key())

    def validate_selected_source(self) -> None:
        self._start_worker("Validating source workflow...", workflow.validate_source_workflow, self.repo_root, self.selected_source_key())

    def validate_reports(self) -> None:
        self._start_worker("Validating TSV reports...", workflow.validate_reports, self.repo_root, self.selected_source_key())

    def export_tsv_package(self) -> None:
        self._start_worker("Exporting TSV package...", workflow.export_tsv_package, self.repo_root, self.selected_source_key())

    def _start_worker(self, label: str, target: Any, *args: Any) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(APP_NAME, "A workflow is already running. Let it finish before starting another one.")
            return
        self.current_action_var.set(label)
        self.counter_var.set("")
        self.progress.configure(value=8)
        self.next_action_var.set("Working. Progress and results will appear here.")
        self.worker_thread = threading.Thread(target=self._worker_wrapper, args=(target, args), daemon=True)
        self.worker_thread.start()

    def _worker_wrapper(self, target: Any, args: tuple[Any, ...]) -> None:
        try:
            result = target(*args)
            self.worker_queue.put({"kind": "done", "result": result})
        except Exception as exc:
            self.worker_queue.put({"kind": "error", "error": str(exc), "traceback": traceback.format_exc()})

    def _poll_worker_queue(self) -> None:
        try:
            while True:
                message = self.worker_queue.get_nowait()
                if message["kind"] == "done":
                    result = message.get("result", {})
                    self.progress.configure(value=100)
                    self.current_action_var.set(self.completion_text(result))
                    self.counter_var.set(self.counter_text(result))
                    self.append_log(json.dumps(self.safe_result_for_log(result), indent=2))
                    self.refresh_sources()
                    if self.selected_key:
                        self.load_source(self.selected_key)
                    self.show_result_popup(result)
                else:
                    self.progress.configure(value=0)
                    self.current_action_var.set("Workflow failed")
                    self.append_log(message.get("error", "Unknown error"))
                    self.append_log(message.get("traceback", ""))
                    messagebox.showerror(APP_NAME, f"The workflow stopped before it could finish.\n\nWhat happened: {message.get('error', 'Unknown error')}\n\nWhat to do: check the source setup and logs, then run validation or try the action again.")
        except queue.Empty:
            pass
        self.after(100, self._poll_worker_queue)

    def safe_result_for_log(self, result: Any) -> Any:
        if isinstance(result, dict):
            return {key: self.safe_result_for_log(value) for key, value in result.items()}
        if isinstance(result, list):
            return [self.safe_result_for_log(value) for value in result]
        if isinstance(result, str):
            return workflow.redact_url(result)
        return result

    def completion_text(self, result: dict[str, Any]) -> str:
        if "fetch" in result and "parse" in result:
            return "Full inventory completed" if result.get("ok") else "Full inventory completed with validation issues"
        if "manifest_rows" in result:
            failed = sum(1 for row in result["manifest_rows"] if row.get("status") == "error")
            return "Fetch completed" if not failed else f"Fetch completed with {failed} provider error(s)"
        if "all_stream_records" in result:
            return "Inventory parsed and reports exported"
        if "package_path" in result:
            return "TSV package exported"
        if "errors" in result:
            return "Validation passed" if result.get("ok") else "Validation found issues"
        return "Complete"

    def counter_text(self, result: dict[str, Any]) -> str:
        parse = result.get("parse", result)
        if isinstance(parse, dict) and "all_stream_records" in parse:
            return f"Records {parse.get('all_stream_records', 0):,} | Live {parse.get('live_tv_channels', 0):,} | Movies {parse.get('vod_movies', 0):,} | Shows {parse.get('series', 0):,}"
        if "manifest_rows" in result:
            ok = sum(1 for row in result["manifest_rows"] if row.get("status") == "ok")
            return f"Files {ok}/{len(result['manifest_rows'])}"
        return ""

    def show_result_popup(self, result: dict[str, Any]) -> None:
        if "fetch" in result and "parse" in result:
            parse = result["parse"]
            self.next_action_var.set("Next: open Inventory Preview or Reports and Filters to review the provider inventory.")
            messagebox.showinfo(APP_NAME, f"Full inventory finished.\n\nRecords: {parse.get('all_stream_records', 0):,}\nLive TV: {parse.get('live_tv_channels', 0):,}\nMovies: {parse.get('vod_movies', 0):,}\nShows: {parse.get('series', 0):,}\nTV guide programmes: {parse.get('epg_programmes', 0):,}\n\nLatest reports:\n{parse.get('latest_report', '')}")
            return
        if "manifest_rows" in result:
            failed = [row for row in result["manifest_rows"] if row.get("status") == "error"]
            if failed:
                details = "\n".join(f"- {row.get('file_label')}: {row.get('error')}" for row in failed[:6])
                messagebox.showwarning(APP_NAME, f"Some provider files did not download.\n\n{details}\n\nThe app will still use any playlist, TV guide, or Xtream metadata that was captured locally.")
        elif "all_stream_records" in result:
            messagebox.showinfo(APP_NAME, f"Reports exported.\n\nRecords: {result.get('all_stream_records', 0):,}\nLatest report folder:\n{result.get('latest_report', '')}")
        elif "package_path" in result:
            messagebox.showinfo(APP_NAME, f"TSV package exported.\n\n{result.get('package_path')}")
        elif "errors" in result and not result.get("ok"):
            messagebox.showwarning(APP_NAME, "Validation found issues.\n\n" + "\n".join(result.get("errors", [])[:10]))

    def update_summary(self) -> None:
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        if not self.selected_key:
            self.summary_text.insert("end", "No source selected.\n\nPaste a provider URL or choose a saved source.")
            self.summary_text.configure(state="disabled")
            return
        profile = self.profiles.get(self.selected_key, {})
        counts = workflow.latest_report_counts(self.repo_root, self.selected_key)
        private = workflow.load_private_profiles(self.repo_root).get(self.selected_key, {})
        lines = [
            f"Source Name: {profile.get('source_display_name', '')}",
            f"Source ID: {self.selected_key}",
            f"Source Type: {profile.get('source_type', '')}",
            f"Status: {self.status_label(profile.get('source_status', 'configured'))}",
            f"Last Fetch: {profile.get('last_fetch_at', '') or 'None'}",
            f"Last Parse: {profile.get('last_parse_at', '') or 'None'}",
            "",
            f"M3U/API records: {counts['m3u_records']:,}",
            f"EPG channels: {counts['epg_channels']:,}",
            f"EPG programmes: {counts['epg_programmes']:,}",
            f"Live TV: {counts['live_tv']:,}",
            f"Movies: {counts['movies']:,}",
            f"Series: {counts['series']:,}",
            f"Report status: {'Complete' if counts['report_exists'] else 'Missing'}",
            f"Credential status: {'Local credentials found' if private else 'Missing credentials'}",
        ]
        self.summary_text.insert("end", "\n".join(lines))
        self.summary_text.configure(state="disabled")

    def view_source_status(self) -> None:
        status = workflow.local_dataset_status(self.repo_root, self.selected_source_key())
        counts = workflow.latest_report_counts(self.repo_root, self.selected_source_key())
        files = "\n".join(f"- {Path(item['path']).name}: {'exists' if item['exists'] else 'missing'} ({item['bytes']:,} bytes)" for item in status["files"])
        messagebox.showinfo(APP_NAME, f"Source Status\n\nLocal files:\n{files}\n\nReports: {'found' if counts['report_exists'] else 'missing'}\nFiltered feed folder:\n{workflow.source_paths(self.repo_root, self.selected_source_key(), 'status').web_feed_dir}")

    def load_filter_values(self) -> None:
        if not self.selected_key or not hasattr(self, "value_listbox"):
            return
        field = FIELD_BY_LABEL.get(self.rule_field_label_var.get(), "group_title")
        search = self.rule_search_var.get()
        if field == "item_type":
            raw_counts = workflow.scope_value_counts(self.repo_root, self.selected_key, field, search, 1000)
            rows = [{"value": CONTENT_TYPE_LABELS.get(row["value"], row["value"]), "raw_value": row["value"], "count": row["count"]} for row in raw_counts]
        else:
            rows = [row | {"raw_value": row["value"]} for row in workflow.scope_value_counts(self.repo_root, self.selected_key, field, search, 1000)]
        self.value_list_data = rows
        self.value_listbox.delete(0, "end")
        for row in rows:
            self.value_listbox.insert("end", f"{row['value']} ({row['count']:,})")
        self.rule_preview_var.set(f"{len(rows):,} values loaded from latest parsed data.")

    def selected_filter_values(self) -> list[str]:
        values = []
        for index in self.value_listbox.curselection():
            row = self.value_list_data[index]
            values.append(row.get("raw_value", row.get("value", "")))
        return values

    def preview_scope_count(self) -> None:
        try:
            values = self.selected_filter_values()
            count = workflow.preview_scope_rule_count(self.repo_root, self.selected_source_key(), FIELD_BY_LABEL.get(self.rule_field_label_var.get(), "group_title"), self.rule_operator_var.get(), values)
            self.rule_preview_var.set(f"{count:,} records match the selected value(s).")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The filter preview could not be calculated.\n\nWhat happened: {exc}\n\nWhat to do: run Parse Inventory first, then reload values.")

    def save_scope_rule(self) -> None:
        try:
            values = self.selected_filter_values()
            if not values:
                messagebox.showinfo(APP_NAME, "Select one or more values before adding a filter rule.")
                return
            field = FIELD_BY_LABEL.get(self.rule_field_label_var.get(), "group_title")
            operator = "in_list" if len(values) > 1 else self.rule_operator_var.get()
            rule_value = ",".join("" if value == "(blank / unknown)" else value for value in values)
            paths = workflow.source_paths(self.repo_root, self.selected_source_key(), "rules")
            rules = workflow.load_scope_rules(paths.scope_dir)
            rules.append({"action": self.rule_action_var.get(), "field_name": field, "operator": operator, "value": rule_value, "case_sensitive": "N", "enabled": "Y", "notes": f"Created from GUI label {self.rule_field_label_var.get()}"})
            workflow.write_tsv(paths.scope_dir / "scope_rules.tsv", rules, workflow.SCOPE_RULE_FIELDS)
            self.load_scope_rules_view()
            self.append_log(f"Saved filter rule for {self.selected_source_key()}: {self.rule_action_var.get()} {self.rule_field_label_var.get()}")
            self.next_action_var.set("Next: click Apply and Export to rebuild the filtered source playlist and TV guide.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The filter rule could not be saved.\n\nWhat happened: {exc}")

    def load_scope_rules_view(self) -> None:
        if not hasattr(self, "scope_rules_tree") or not self.selected_key:
            return
        for item in self.scope_rules_tree.get_children():
            self.scope_rules_tree.delete(item)
        rules = workflow.load_scope_rules(workflow.source_paths(self.repo_root, self.selected_key, "rules").scope_dir)
        for index, rule in enumerate(rules):
            label = UI_FIELDS.get(rule.get("field_name", ""), rule.get("field_name", ""))
            self.scope_rules_tree.insert("", "end", iid=str(index), values=(rule.get("action", ""), label, rule.get("operator", ""), rule.get("value", ""), rule.get("enabled", ""), rule.get("notes", "")))

    def remove_selected_scope_rule(self) -> None:
        try:
            selected = self.scope_rules_tree.selection()
            if not selected:
                messagebox.showinfo(APP_NAME, "Select one or more filter rules first.")
                return
            indexes = {int(item) for item in selected}
            paths = workflow.source_paths(self.repo_root, self.selected_source_key(), "rules")
            rules = workflow.load_scope_rules(paths.scope_dir)
            workflow.write_tsv(paths.scope_dir / "scope_rules.tsv", [rule for index, rule in enumerate(rules) if index not in indexes], workflow.SCOPE_RULE_FIELDS)
            self.load_scope_rules_view()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The selected filter rule could not be removed.\n\nWhat happened: {exc}")

    def clear_scope_rules(self) -> None:
        try:
            if not messagebox.askyesno(APP_NAME, "Clear all filter rules for this source?"):
                return
            paths = workflow.source_paths(self.repo_root, self.selected_source_key(), "rules")
            workflow.write_tsv(paths.scope_dir / "scope_rules.tsv", [], workflow.SCOPE_RULE_FIELDS)
            self.load_scope_rules_view()
            self.rule_preview_var.set("Filter rules cleared.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Filter rules could not be cleared.\n\nWhat happened: {exc}")

    def read_latest_tsv(self, file_name: str, limit: int = 5000) -> list[dict[str, str]]:
        path = workflow.source_paths(self.repo_root, self.selected_source_key(), "report").latest_report / file_name
        if not path.exists():
            raise FileNotFoundError(f"Run Full Inventory to create {file_name}.")
        rows: list[dict[str, str]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle, delimiter="\t")):
                if index >= limit:
                    break
                rows.append(dict(row))
        return rows

    def load_report_view(self, report_type: str) -> None:
        try:
            config = {
                "groups": ("m3u_group_summary.tsv", ["item_type", "group_title", "record_count"]),
                "live": ("live_tv_channels.tsv", ["raw_title", "xtream_category_name", "group_title", "country_normalized", "language_normalized", "network_normalized"]),
                "movies": ("vod_movies.tsv", ["raw_title", "xtream_category_name", "group_title", "country_normalized", "language_normalized"]),
                "series": ("series.tsv", ["raw_title", "xtream_category_name", "group_title", "country_normalized", "language_normalized"]),
                "epg_channels": ("epg_channels.tsv", ["epg_channel_id", "display_name_primary", "matched_m3u_title", "match_method", "match_confidence"]),
                "epg_programmes": ("epg_programmes.tsv", ["title", "channel_id", "start_local", "stop_local", "category_all", "country", "language"]),
            }[report_type]
            rows = self.read_latest_tsv(config[0])
            columns = [UI_FIELDS.get(column, {"record_count": "Count", "item_type": "Content Type", "xtream_category_name": "Category", "display_name_primary": "Display Name", "epg_channel_id": "TV Guide Channel ID", "matched_m3u_title": "Matched Channel", "match_method": "Match Method", "match_confidence": "Match Confidence", "title": "Title", "channel_id": "Channel ID", "start_local": "Start", "stop_local": "Stop", "category_all": "Categories"}.get(column, column)) for column in config[1]]
            self.report_tree.configure(columns=columns)
            for item in self.report_tree.get_children():
                self.report_tree.delete(item)
            for label in columns:
                self.report_tree.heading(label, text=label)
                self.report_tree.column(label, width=220 if label in {"Original Title", "Title", "Group", "Category"} else 140, anchor="w")
            for index, row in enumerate(rows):
                values = []
                for field in config[1]:
                    value = row.get(field, "")
                    if field == "item_type":
                        value = CONTENT_TYPE_LABELS.get(value, value)
                    values.append(value)
                self.report_tree.insert("", "end", iid=str(index), values=values)
            self.main_notebook.select(self.inventory_tab)
            self.append_log(f"Loaded {len(rows):,} rows from {config[0]}.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"The report could not be opened.\n\nWhat happened: {exc}\n\nWhat to do: run Full Inventory or Parse Inventory for this source, then open the report again.")

    def focus_source_editor(self) -> None:
        self.main_notebook.select(self.dashboard_tab)

    def focus_export_settings(self) -> None:
        self.main_notebook.select(self.dashboard_tab)
        messagebox.showinfo(APP_NAME, "Export settings are on the Dashboard under Advanced Actions. Filtered playlist and TV guide export is controlled by the Parse Inventory workflow.")

    def reset_layout(self) -> None:
        self.geometry("1500x980")
        self.main_notebook.select(self.dashboard_tab)

    def open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(path))
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def open_file(self, path: Path) -> None:
        if hasattr(os, "startfile"):
            os.startfile(str(path))
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def open_latest_report_folder(self, source_key: str | None = None) -> None:
        key = workflow.clean_source_key(source_key or self.selected_source_key())
        self.open_path(workflow.source_paths(self.repo_root, key, "open").latest_report)

    def open_source_data_folder(self) -> None:
        self.open_path(workflow.source_paths(self.repo_root, self.selected_source_key(), "open").web_feed_dir)

    def open_source_filters_folder(self) -> None:
        self.open_path(workflow.source_paths(self.repo_root, self.selected_source_key(), "open").scope_dir)

    def open_reference_locations(self) -> None:
        self.open_path(self.repo_root / "data")

    def open_workflow_guide(self) -> None:
        self.open_file(self.repo_root / "docs" / "iptv_multi_source_parser.html")

    def show_field_dictionary(self) -> None:
        text = "\n".join(f"{label} -> {field}: shown in the GUI as {label}; TSV field {field}; value comes from M3U, XMLTV, Xtream API, or repo reference data with derivation/confidence columns where applicable." for field, label in sorted(UI_FIELDS.items(), key=lambda item: item[1]))
        self.show_text_window("Field Dictionary", text)

    def show_troubleshooting(self) -> None:
        self.show_text_window("Troubleshooting", "If a playlist fetch fails but TV guide or Xtream metadata succeeds, run Parse Inventory anyway. The parser can inventory Xtream API records when the provider blocks playlist export. Use Validate Reports after parsing to confirm the TSV package is complete.")

    def show_about(self) -> None:
        messagebox.showinfo(APP_NAME, f"{APP_NAME} {APP_VERSION}\n\nMulti-source IPTV inventory, review, filtering, and source-specific feed export.")

    def show_text_window(self, title: str, text: str) -> None:
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("760x520")
        area = tk.Text(window, wrap="word")
        area.pack(fill="both", expand=True)
        area.insert("1.0", text)
        area.configure(state="disabled")


def main() -> int:
    app = MultiSourceGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
