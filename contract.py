"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    GENERATE_LOG = "generate_log"
    MINE_TEMPLATES = "mine_templates"


class Task(Enum):
    GENERATE_LOG = "generate-log"
    MINE_LOG_TEMPLATES = "mine-log-templates"
    FIND_SPIKING_ERROR = "find-spiking-error"


SEED = "The scenario's seed: the same seed and line count always give the same file, byte for byte"
LINES = "How many lines the log holds, 500 to 100000, one per second from 2026-10-31T12:00:00Z"
DESTINATION = "The folder relative to the plugin workspace the log is saved in, e.g. logs"
FILE = "The log, relative to the plugin workspace: <destination>/app-<seed>-<lines>.log"
SHA256 = "The SHA-256 of the file's bytes, lowercase hex"
TEMPLATE = (
    "A line's template: 'LEVEL service masked-message'. The message is masked in this order: every double-quoted"
    ' string becomes "<STR>"; every UUID becomes <UUID>; every IPv4 address, with or without :port, becomes <IP>;'
    " every 0x-prefixed hex number, and every standalone run of 8 or more hex characters holding a digit, becomes"
    " <HEX>; then the message is split on whitespace, every token still holding a digit becomes <NUM>, and the"
    " tokens are joined with single spaces"
)


@dataclass
class GenerateInput(Output):
    seed: Annotated[int, SEED]
    lines: Annotated[int, LINES]
    destination: Annotated[str, DESTINATION]


@dataclass
class GenerateOutput(Output):
    file: Annotated[str, FILE]
    lines: Annotated[int, "How many lines the file holds, each '<timestamp> <LEVEL> <service> <message>'"]
    sha256: Annotated[str, SHA256]


@dataclass
class MineInput(Output):
    file: Annotated[str, "A log relative to the plugin workspace, e.g. logs/app-7-20000.log"]
    start_line: Annotated[int, "The window's first line, 1-based and inclusive, at least 1"]
    end_line: Annotated[int, "The window's last line, inclusive: at least start_line and at most the file's last line"]
    top: Annotated[int, "How many of the most frequent templates to return, 1 to 200"]


@dataclass
class TemplateCount(Output):
    template: Annotated[str, TEMPLATE]
    count: Annotated[int, "How many lines in the window have this template"]
    first_line: Annotated[int, "The 1-based line number of its first line in the window"]


@dataclass
class MineOutput(Output):
    file: Annotated[str, "The log, as given"]
    start_line: Annotated[int, "The window's first line, as given"]
    end_line: Annotated[int, "The window's last line, as given"]
    lines: Annotated[int, "How many lines the window holds, end_line - start_line + 1"]
    distinct: Annotated[int, "How many distinct templates the window holds"]
    templates: Annotated[
        list[TemplateCount],
        "The window's templates by count, highest first, ties by template text; only the first top of them",
    ]


@dataclass
class SpikeInput(Output):
    seed: Annotated[int, SEED]
    lines: Annotated[int, LINES]


@dataclass
class SpikeOutput(Output):
    file: Annotated[str, "The log generated for the seed and line count, logs/app-<seed>-<lines>.log"]
    template: Annotated[str, "The ERROR template whose count grew the most from the first half to the second half"]
    first_half_count: Annotated[int, "That template's count in lines 1 to lines // 2"]
    second_half_count: Annotated[int, "That template's count in lines lines // 2 + 1 to lines"]


TOOLS = {
    Tool.GENERATE_LOG: (GenerateInput, GenerateOutput),
    Tool.MINE_TEMPLATES: (MineInput, MineOutput),
}
TASKS = {
    Task.GENERATE_LOG: (GenerateInput, GenerateOutput),
    Task.MINE_LOG_TEMPLATES: (MineInput, MineOutput),
    Task.FIND_SPIKING_ERROR: (SpikeInput, SpikeOutput),
}
