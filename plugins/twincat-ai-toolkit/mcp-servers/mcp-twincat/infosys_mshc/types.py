"""Type definitions and data structures for InfoSys MSHC."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, TypedDict


class ParamItem(TypedDict, total=False):
    """Parameter / Variable row from an input/output/parameter table."""

    name: str
    type: str
    description: str


class MethodItem(TypedDict, total=False):
    """Method entry extracted from methods table or list."""

    name: str
    description: str
    signature: str


@dataclass
class PropertyItem:
    """Property entry extracted from properties / Eigenschaften section."""

    name: str
    type: str
    description: str = ""
    access: str = "Get/Set"

    def to_dict(self) -> Dict[str, str]:
        d: Dict[str, str] = {
            "name": self.name,
            "type": self.type,
            "access": self.access,
        }
        if self.description:
            d["description"] = self.description
        return d


class RequirementsInfo(TypedDict, total=False):
    """Requirements info extracted from requirements section or metadata."""

    library: str
    twincat_version: str
    development_environment: str
    target_platform: str


@dataclass
class DocEntry:
    """An indexed documentation page metadata entry."""

    title: str
    type: str
    component: str
    path: str
    library: str = ""
    parent: str = ""
    qualified_name: str = ""
    description: str = ""
    canonical_name: str = ""

    def to_dict(self) -> Dict[str, str]:
        d: Dict[str, str] = {
            "title": self.title,
            "type": self.type,
            "component": self.component,
            "path": self.path,
            "library": self.library,
            "parent": self.parent,
            "qualified_name": self.qualified_name,
            "description": self.description,
        }
        if self.canonical_name:
            d["canonical_name"] = self.canonical_name
        return d


@dataclass
class SearchResultItem:
    """A scored result item from an index search."""

    title: str
    type: str
    component: str
    path: str
    score: int
    library: str = ""
    parent: str = ""
    qualified_name: str = ""
    description: str = ""
    snippet: str = ""
    canonical_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "title": self.title,
            "type": self.type,
            "component": self.component,
            "path": self.path,
            "score": self.score,
        }
        if self.library:
            d["library"] = self.library
        if self.parent:
            d["parent"] = self.parent
        if self.qualified_name:
            d["qualified_name"] = self.qualified_name
        if self.description:
            d["description"] = self.description
        if self.snippet:
            d["snippet"] = self.snippet
        if self.canonical_name:
            d["canonical_name"] = self.canonical_name
        return d


@dataclass
class SearchResponse:
    """Overall response object for an MSHC search."""

    query: str
    mode: str
    count: int
    results: List[Dict[str, Any]] = field(default_factory=list)
    auto_read: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "query": self.query,
            "mode": self.mode,
            "count": self.count,
            "results": self.results,
        }
        if self.auto_read is not None:
            d["auto_read"] = self.auto_read
        return d


@dataclass
class PageResult:
    """Structured extraction result of an InfoSys documentation page."""

    title: str
    component: str
    type: str
    path: str
    canonical_name: str
    library: str = ""
    parent: str = ""
    qualified_name: str = ""
    description: str = ""
    syntax: str = ""
    return_type: Optional[str] = None
    inputs: List[ParamItem] = field(default_factory=list)
    outputs: List[ParamItem] = field(default_factory=list)
    parameters: List[ParamItem] = field(default_factory=list)
    methods: List[MethodItem] = field(default_factory=list)
    properties: List[PropertyItem] = field(default_factory=list)
    requirements: Dict[str, str] = field(default_factory=dict)
    full_text: str = ""
    truncated: bool = False
    full_text_included: bool = False
    total_full_text_chars: int = 0
    methods_total: int = 0
    methods_shown: int = 0
    params_total: int = 0
    params_shown: int = 0

    @property
    def sym_type(self) -> str:
        """IEC 61131-3 symbol type alias for structured consumers."""
        return self.type

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "title": self.title,
            "canonical_name": self.canonical_name,
            "component": self.component,
            "type": self.type,
            "sym_type": self.type,
            "path": self.path,
        }
        if self.library:
            res["library"] = self.library
        if self.parent:
            res["parent"] = self.parent
        if self.qualified_name:
            res["qualified_name"] = self.qualified_name
        res["description"] = self.description
        res["syntax"] = self.syntax
        if self.return_type:
            res["return_type"] = self.return_type

        if self.inputs:
            res["inputs"] = self.inputs
        if self.outputs:
            res["outputs"] = self.outputs
        if self.parameters:
            res["parameters"] = self.parameters
        if self.methods:
            res["methods"] = self.methods
        if self.properties:
            res["properties"] = [p.to_dict() if isinstance(p, PropertyItem) else p for p in self.properties]
        if self.requirements:
            res["requirements"] = self.requirements
        res["full_text"] = self.full_text
        res["truncated"] = self.truncated
        res["full_text_included"] = self.full_text_included
        res["total_full_text_chars"] = self.total_full_text_chars
        if self.methods_total > 0:
            res["methods_total"] = self.methods_total
            res["methods_shown"] = self.methods_shown
        if self.params_total > 0:
            res["params_total"] = self.params_total
            res["params_shown"] = self.params_shown
        return res
