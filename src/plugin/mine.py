"""mine_templates: collapse a window of log lines into templates by masking their variable fields."""

import re
from collections import Counter
from pathlib import Path

from contract import MineInput, MineOutput, TemplateCount

MAX_TOP = 200
LEVELS = ("INFO", "WARN", "ERROR")
# The masking rules, applied in this order to the message part of a line.
QUOTED = re.compile(r'"[^"]*"', re.ASCII)
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", re.ASCII)
IPV4 = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?(?![\w.])", re.ASCII)
HEX = re.compile(r"\b0[xX][0-9a-fA-F]+\b|(?<![\w])(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{8,}(?![\w])", re.ASCII)
DIGIT = re.compile(r"\d", re.ASCII)


def mask(message: str) -> str:
    message = QUOTED.sub('"<STR>"', message)
    message = UUID.sub("<UUID>", message)
    message = IPV4.sub("<IP>", message)
    message = HEX.sub("<HEX>", message)
    return " ".join("<NUM>" if DIGIT.search(token) else token for token in message.split())


def template_of(line: str) -> str | None:
    """The line's template 'LEVEL service masked-message', or None when the line is not a log line."""
    parts = line.split(" ", 3)
    if len(parts) != 4 or not parts[0] or parts[1] not in LEVELS or not parts[2]:
        return None
    return f"{parts[1]} {parts[2]} {mask(parts[3])}"


def read_lines(workspace: Path, file: str) -> list[str]:
    path = Path(file)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".log":
        raise ValueError(f"file {file!r} must be a .log inside the plugin workspace")
    target = workspace / path
    if not target.is_file():
        raise FileNotFoundError(f"{file} is not in the workspace: generate it with generate_log first")
    return target.read_text(encoding="utf-8").splitlines()


def mine_templates(given: MineInput, workspace: Path) -> MineOutput:
    if not 1 <= given.top <= MAX_TOP:
        raise ValueError(f"top must be between 1 and {MAX_TOP}, got {given.top}")
    if not 1 <= given.start_line <= given.end_line:
        raise ValueError(f"need 1 <= start_line <= end_line, got {given.start_line} and {given.end_line}")
    lines = read_lines(workspace, given.file)
    if given.end_line > len(lines):
        raise ValueError(f"end_line {given.end_line} is past the file's last line, {len(lines)}")
    counts: Counter[str] = Counter()
    first: dict[str, int] = {}
    for number in range(given.start_line, given.end_line + 1):
        template = template_of(lines[number - 1])
        if template is None:
            raise ValueError(f"{given.file} line {number} is not '<timestamp> <LEVEL> <service> <message>'")
        counts[template] += 1
        first.setdefault(template, number)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: given.top]
    return MineOutput(
        file=given.file,
        start_line=given.start_line,
        end_line=given.end_line,
        lines=given.end_line - given.start_line + 1,
        distinct=len(counts),
        templates=[TemplateCount(template=text, count=count, first_line=first[text]) for text, count in ranked],
    )
