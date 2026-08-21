"""Type definitions and data structures for InfoSys MSHC."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "type": self.type,
            "component": self.component,
            "path": self.path,
            "description": self.description,
        }


@dataclass
class SearchResultItem:
    """A scored result item from an index search."""

    title: str
    type: str
    component: str
    path: str
    score: int
    description: str = ""
    snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "title": self.title,
            "type": self.type,
            "component": self.component,
            "path": self.path,
            "score": self.score,
        }
        if self.description:
            d["description"] = self.description
        if self.snippet:
            d["snippet"] = self.snippet
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
    description: str = ""
    syntax: str = ""
    inputs: List[ParamItem] = field(default_factory=list)
    outputs: List[ParamItem] = field(default_factory=list)
    parameters: List[ParamItem] = field(default_factory=list)
    methods: List[MethodItem] = field(default_factory=list)
    requirements: Dict[str, str] = field(default_factory=dict)
    full_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "title": self.title,
            "component": self.component,
            "type": self.type,
            "path": self.path,
            "description": self.description,
            "syntax": self.syntax,
        }
        if self.inputs:
            res["inputs"] = self.inputs
        if self.outputs:
            res["outputs"] = self.outputs
        if self.parameters:
            res["parameters"] = self.parameters
        if self.methods:
            res["methods"] = self.methods
        if self.requirements:
            res["requirements"] = self.requirements
        res["full_text"] = self.full_text
        return res
