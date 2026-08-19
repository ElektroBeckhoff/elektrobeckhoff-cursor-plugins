"""CFC graph data model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PinInfo:
    pin_id: int = 0
    owner_id: int = 0
    pin_type: str = ""          # "input" | "output" | "inout"
    name: str = ""
    negated: bool = False
    set_reset: str = "None"     # "None" | "Set" | "Reset"
    index: int = 0


@dataclass
class CFCElement:
    element_id: int = 0
    element_type: str = ""      # "input" | "output" | "box" | "connection"
    var_name: str = ""
    kind_of_call: str = ""      # "Operator" | "FunctionBlock"
    box_type: str = ""
    instance_name: str = ""
    input_pins: List[PinInfo] = field(default_factory=list)
    output_pins: List[PinInfo] = field(default_factory=list)
    inout_pins: List[PinInfo] = field(default_factory=list)
    en_eno: bool = False
    texts: List[str] = field(default_factory=list)
    bounds: str = ""


@dataclass
class CFCConnection:
    source_pin_id: int = 0
    dest_pin_id: int = 0


@dataclass
class CFCGraph:
    elements: Dict[int, CFCElement] = field(default_factory=dict)
    pins: Dict[int, PinInfo] = field(default_factory=dict)
    connections: List[CFCConnection] = field(default_factory=list)
    edges: Dict[int, int] = field(default_factory=dict)
    reverse_edges: Dict[int, List[int]] = field(default_factory=dict)
    execution_order: List[CFCElement] = field(default_factory=list)
    mark_sources: Dict[str, int] = field(default_factory=dict)
