"""TwinCAT 3 graphical-to-ST migration package."""
from __future__ import annotations

from migrator.codegen import convert_networks_to_st
from migrator.constants import SCRIPT_VERSION, SUPPORTED_EXTENSIONS
from migrator.io_utils import collect_input_files, create_backup, write_output_file
from migrator.cli import load_config, parse_arguments
from migrator.reporting import MigrationLogger, MigrationReport
from migrator.types import (
    ActionInfo,
    AssignNode,
    BoxNode,
    DemuxNode,
    MigrationConfig,
    NwlNetwork,
    OperandNode,
    StNetwork,
    TcFile,
)
from migrator.validation import build_generated_header, calculate_accuracy, validate_generated_st
from migrator.xml_reader import load_file

__all__ = [
    # Package metadata
    "SCRIPT_VERSION",
    "SUPPORTED_EXTENSIONS",
    # IR classes
    "ActionInfo",
    "AssignNode",
    "BoxNode",
    "DemuxNode",
    "MigrationConfig",
    "MigrationLogger",
    "MigrationReport",
    "NwlNetwork",
    "OperandNode",
    "StNetwork",
    "TcFile",
    # CLI / I/O
    "parse_arguments",
    "load_config",
    "collect_input_files",
    "load_file",
    "write_output_file",
    "create_backup",
    # Codegen / validation
    "convert_networks_to_st",
    "validate_generated_st",
    "build_generated_header",
    "calculate_accuracy",
]
