"""IR dataclasses for TwinCAT graphical-to-ST migration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class OperandNode:
    name: str = ""
    type_str: str = ""
    is_lvalue: bool = False
    is_instance: bool = False
    flags: int = 0
    xml_id: str = ""
    comment: str = ""
    is_null: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.name or self.name == '""' or self.name == ""


@dataclass
class BoxNode:
    box_type: str = ""
    call_type: str = ""
    instance: Optional[OperandNode] = None
    input_items: List[Union[BoxNode, OperandNode]] = field(default_factory=list)
    output_items: List[OperandNode] = field(default_factory=list)
    input_param_names: List[str] = field(default_factory=list)
    input_param_types: List[str] = field(default_factory=list)
    output_param_names: List[str] = field(default_factory=list)
    output_param_types: List[str] = field(default_factory=list)
    input_flags: List[int] = field(default_factory=list)
    en: bool = False
    eno: bool = False
    st_snippet: List[str] = field(default_factory=list)
    xml_id: str = ""


@dataclass
class DemuxNode:
    input: Optional[OperandNode] = None
    xml_id: str = ""


@dataclass
class AssignNode:
    outputs: List[OperandNode] = field(default_factory=list)
    rvalue: Optional[Union[BoxNode, OperandNode, "AssignNode", DemuxNode]] = None
    flags: int = 0
    xml_id: str = ""


@dataclass
class NwlNetwork:
    index: int = 0
    comment: str = ""
    title: str = ""
    label: str = ""
    out_commented: bool = False
    items: List[Union[BoxNode, AssignNode, DemuxNode]] = field(default_factory=list)
    xml_id: str = ""


@dataclass
class ActionInfo:
    name: str = ""
    impl_type: str = ""
    networks: List[NwlNetwork] = field(default_factory=list)
    st_code: str = ""
    xml_element: Any = None


@dataclass
class StNetwork:
    index: int = 0
    comment_header: str = ""
    lines: List[str] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)
    out_commented: bool = False


@dataclass
class TcFile:
    path: Path = field(default_factory=Path)
    file_type: str = ""
    encoding: str = "utf-8"
    xml_tree: Any = None
    xml_root: Any = None
    pou_name: str = ""
    pou_type: str = ""
    pou_id: str = ""
    special_func: str = ""
    declaration: str = ""
    impl_type: str = ""
    networks: List[NwlNetwork] = field(default_factory=list)
    actions: List[ActionInfo] = field(default_factory=list)
    generated_st: str = ""
    st_networks: List[StNetwork] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    edge_vars: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class MigrationConfig:
    input_path: str = ""
    output_path: str = ""
    recursive: bool = False
    backup: bool = True
    force: bool = False
    swap: bool = False
    batch_dir: Optional[str] = None
    backup_dir: Optional[str] = None
    dry_run: bool = False
    analyze_only: bool = False
    log_enabled: bool = True
    report_enabled: bool = True
    config_file: str = ""
    encoding: str = "utf-8"
    strict: bool = False
    preserve_ids: bool = True
    preserve_comments: bool = True
    mark_todo: bool = True
    fail_on_unclear: bool = True
    log_level: str = "INFO"
