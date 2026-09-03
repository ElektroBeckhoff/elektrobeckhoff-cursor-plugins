"""Result dataclasses for TwinCAT Automation Interface operations."""
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class StatusResult:
    xae_available: bool
    running_instance: bool
    solution_path: str = ""
    plc_project_name: str = ""
    message: str = ""
    instances: list = field(default_factory=list)
    mcp_session_active: bool = False
    mcp_solution_path: str = ""
    mcp_plc_project_name: str = ""
    silent_mode: Optional[bool] = None
    blocking_dialogs: list = field(default_factory=list)
    dismissed_dialogs_recent: list = field(default_factory=list)
    sys_manager_errors: str = ""
    twincat_runtime_started: Optional[bool] = None
    target_net_id: str = ""
    prereqs: dict = field(default_factory=dict)
    mcp_server_version: str = ""
    log_file: str = ""


@dataclass
class OpenResult:
    success: bool
    solution_path: str = ""
    plc_project_name: str = ""
    created_new_instance: bool = False
    xae_prog_id: str = ""
    xae_version: str = ""
    message: str = ""
    requested_xae_version: str = ""
    attached_xae_version: str = ""
    attached_instance_id: str = ""
    pin_honored: Optional[bool] = None
    pin_ignored_reason: str = ""
    open_solutions: list = field(default_factory=list)


@dataclass
class CheckResult:
    success: bool
    method: str = ""
    error_count: int = 0
    warning_count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    message: str = ""


@dataclass
class BuildResult:
    success: bool
    elapsed_seconds: float = 0.0
    build_state: int = 0
    last_build_info: int = 0
    compile_info_updated: bool = False
    error_count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    message: str = ""


@dataclass
class ErrorEntry:
    severity: str = ""
    description: str = ""
    file_name: str = ""
    line: int = 0
    column: int = 0
    project: str = ""


@dataclass
class ErrorsResult:
    count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    message: str = ""


@dataclass
class ExportResult:
    success: bool
    library_path: str = ""
    compiled_library_path: str = ""
    library_size_kb: float = 0.0
    compiled_library_size_kb: float = 0.0
    message: str = ""
    resolved_plcproj_path: str = ""
    project_title: str = ""
    project_version: str = ""
    output_dir: str = ""
    # True when wait=false started a background job (poll twincat_export_progress).
    async_started: bool = False
    method: str = ""
    # True when every requested artifact exists on disk with size > 0.
    artifacts_on_disk: bool = False
    # [{path, size_kb, kind, exists}] for requested outputs.
    artifacts: list = field(default_factory=list)


@dataclass
class ExportArtifactsCheckResult:
    """Filesystem-only check of expected export artifacts (no STA)."""
    success: bool = True
    all_present: bool = False
    output_dir: str = ""
    project_title: str = ""
    project_version: str = ""
    artifacts: list = field(default_factory=list)
    message: str = ""


@dataclass
class DismissSafeDialogsResult:
    """Result of twincat_dismiss_safe_dialogs (idle reload prompts)."""
    success: bool = True
    dismissed_count: int = 0
    dismissed: list = field(default_factory=list)
    remaining_blocking: list = field(default_factory=list)
    message: str = ""


@dataclass
class ExportProgressResult:
    """Live export job progress (readable without STA / while export runs)."""
    success: bool = True
    running: bool = False
    phase: str = "idle"
    output_dir: str = ""
    project_title: str = ""
    project_version: str = ""
    percent: float = 0.0
    started_unix: float = 0.0
    updated_unix: float = 0.0
    elapsed_s: float = 0.0
    message: str = ""
    # Final ExportResult as dict when phase is done/error (async jobs).
    result: Optional[dict] = None
    # Artifact fields mirrored for direct access without extra check_artifacts call
    artifacts_on_disk: bool = False
    artifacts: list = field(default_factory=list)
    library_path: str = ""
    compiled_library_path: str = ""


@dataclass
class ReloadResult:
    success: bool
    elapsed_seconds: float = 0.0
    message: str = ""


@dataclass
class CloseResult:
    success: bool
    message: str = ""


@dataclass
class TargetResult:
    success: bool
    net_id: str = ""
    message: str = ""
    error_code: str = ""
    required_args: list = field(default_factory=list)
    example_next_call: dict = field(default_factory=dict)


@dataclass
class ActivateResult:
    success: bool
    message: str = ""
    error_code: str = ""
    required_args: list = field(default_factory=list)
    example_next_call: dict = field(default_factory=dict)


@dataclass
class StartResult:
    success: bool
    message: str = ""
    error_code: str = ""
    required_args: list = field(default_factory=list)
    example_next_call: dict = field(default_factory=dict)


@dataclass
class TaskListResult:
    success: bool
    tasks: list = field(default_factory=list)
    message: str = ""


@dataclass
class TaskInfoResult:
    success: bool
    task: dict = field(default_factory=dict)
    xml: str = ""
    message: str = ""


# DISABLED_STATE (TCatSysManagerLib) — see InfoSys "Enabling and disabling I/O devices"
SMDS_NOT_DISABLED = 0
SMDS_DISABLED = 1


@dataclass
class IoListResult:
    success: bool
    devices: list = field(default_factory=list)
    message: str = ""


@dataclass
class IoDisableResult:
    success: bool
    path: str = ""
    disabled: Optional[bool] = None
    disabled_raw: Optional[int] = None
    changed: list = field(default_factory=list)
    message: str = ""
    error_code: str = ""
    required_args: list = field(default_factory=list)
    example_next_call: dict = field(default_factory=dict)


@dataclass
class RuntimeMessagesResult:
    success: bool
    twincat_output: str = ""
    build_output_tail: str = ""
    sys_manager_errors: str = ""
    findings: list = field(default_factory=list)
    has_blocking_error: bool = False
    has_blocking_runtime_error: bool = False
    error_count: int = 0
    warning_count: int = 0
    sources: dict = field(default_factory=dict)
    history_incomplete: bool = True
    since_last_activate: bool = False
    message: str = ""
    note: str = ""


@dataclass
class StweepStatusResult:
    success: bool
    installed: bool = False
    version: str = ""
    install_paths: list = field(default_factory=list)
    commands: dict = field(default_factory=dict)
    commands_loaded: bool = False
    dte_attached: bool = False
    license_ok: Optional[bool] = None
    license_state: str = "unknown"
    license_detail: str = ""
    license_days_remain: Optional[int] = None
    license_days_total: Optional[int] = None
    ready: bool = False
    message: str = ""
    # Snapshot from get_format_progress() (no STA); empty when idle.
    format_progress: dict = field(default_factory=dict)


@dataclass
class StweepFormatResult:
    success: bool
    method: str = ""
    command: str = ""
    target: str = ""
    files_total: int = 0
    files_formatted: int = 0
    files_failed: int = 0
    files_unchanged: int = 0
    formatted: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    # Formatcode ran but disk fingerprint unchanged (never dirty, or already OK).
    unchanged: list = field(default_factory=list)
    # True when at least one file's on-disk bytes changed.
    disk_changed: bool = False
    installed: Optional[bool] = None
    license_ok: Optional[bool] = None
    license_state: str = ""
    license_detail: str = ""
    message: str = ""
    # True when wait=false started a background job (poll twincat_stweep_format_progress).
    async_started: bool = False
    # True when twincat_stweep_format_cancel stopped the job mid-loop.
    canceled: bool = False


@dataclass
class StweepFormatCancelResult:
    success: bool
    canceled: bool = False
    was_running: bool = False
    message: str = ""


@dataclass
class StweepFormatProgressResult:
    """Live format job progress (readable without STA / while format runs)."""
    success: bool = True
    running: bool = False
    phase: str = "idle"  # idle | starting | formatting | done | error
    target: str = ""
    files_total: int = 0
    files_done: int = 0
    files_formatted: int = 0
    files_failed: int = 0
    current_file: str = ""
    percent: float = 0.0
    started_unix: float = 0.0
    updated_unix: float = 0.0
    elapsed_s: float = 0.0
    message: str = ""
    # Final StweepFormatResult as dict when phase is done/error (async jobs).
    result: Optional[dict] = None
