"""Checks shared by the tool verifiers. Pure functions of their arguments and the files on disk."""

import re
from collections import Counter
from pathlib import Path

MIN_LINES, MAX_LINES = 500, 100000
MAX_TOP = 200
LEVELS = {"INFO", "WARN", "ERROR"}
HEX_CHARS = "0-9a-fA-F"

# The masking rules, written out on their own from the README.
STRING_RULE = re.compile('"[^"]*"')
UUID_RULE = re.compile(
    "(?<![0-9A-Za-z_])" + "-".join(f"[{HEX_CHARS}]{{{size}}}" for size in (8, 4, 4, 4, 12)) + "(?![0-9A-Za-z_])"
)
IP_RULE = re.compile(r"(?<![0-9A-Za-z_.])[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(:[0-9]{1,5})?(?![0-9A-Za-z_.])")
PREFIXED_HEX_RULE = re.compile(f"(?<![0-9A-Za-z_])0[xX][{HEX_CHARS}]+(?![0-9A-Za-z_])")
LONG_HEX_RULE = re.compile(f"(?<![0-9A-Za-z_])[{HEX_CHARS}]{{8,}}(?![0-9A-Za-z_])")


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def path_problem(relative, suffix=None):
    path = Path(relative)
    if not relative.strip() or path.is_absolute() or ".." in path.parts:
        return f"{relative!r} must stay inside the plugin workspace"
    if suffix and path.suffix != suffix:
        return f"{relative!r} must be a {suffix} file"
    return None


def _long_hex(match):
    text = match.group(0)
    return "<HEX>" if any(character.isdigit() for character in text) else text


def masked(message):
    message = STRING_RULE.sub('"<STR>"', message)
    message = UUID_RULE.sub("<UUID>", message)
    message = IP_RULE.sub("<IP>", message)
    message = PREFIXED_HEX_RULE.sub("<HEX>", message)
    message = LONG_HEX_RULE.sub(_long_hex, message)
    tokens = []
    for token in message.split():
        tokens.append("<NUM>" if any(character in "0123456789" for character in token) else token)
    return " ".join(tokens)


def timestamp(second):
    """The clock time ``second`` seconds after 2026-10-31T12:00:00Z (lines stay under three days)."""
    total = 12 * 3600 + second
    day, rest = divmod(total, 86400)
    date = "2026-10-31" if day == 0 else f"2026-11-{day:02d}"
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{date}T{hours:02d}:{minutes:02d}:{seconds:02d}Z"


def split_line(line):
    """(timestamp, level, service, message), or None when the line is not a log line."""
    parts = line.split(" ", 3)
    if len(parts) != 4 or parts[1] not in LEVELS or not parts[2] or not parts[0]:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def read_log(workspace, relative):
    """The log's lines as (timestamp, level, service, message) tuples, or a string saying why it cannot be read."""
    target = Path(workspace) / relative
    if not target.is_file():
        return f"{relative} is not in the workspace"
    entries = []
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        entry = split_line(line)
        if entry is None:
            return f"{relative} line {number} is not '<timestamp> <LEVEL> <service> <message>'"
        entries.append(entry)
    return entries


def template(entry):
    return f"{entry[1]} {entry[2]} {masked(entry[3])}"


def window_counts(entries, start, end):
    """Each template's count and first 1-based line over lines ``start`` to ``end``, inclusive."""
    counts = Counter()
    first = {}
    for number in range(start, end + 1):
        text = template(entries[number - 1])
        counts[text] += 1
        if text not in first:
            first[text] = number
    return counts, first
