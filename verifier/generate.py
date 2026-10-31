"""generate_log's checks: the file is where the seed names it, whole, its hash is its own, its clock ticks by one."""

import hashlib
from pathlib import Path

from .checks import MAX_LINES, MIN_LINES, path_problem, read_log, result, timestamp


def expected_file(destination, seed, lines):
    return (Path(destination) / f"app-{seed}-{lines}.log").as_posix()


def verify_input(value):
    if not MIN_LINES <= value.lines <= MAX_LINES:
        return result(False, f"lines must be between {MIN_LINES} and {MAX_LINES}")
    problem = path_problem(value.destination)
    if problem:
        return result(False, problem)
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    expected = expected_file(input_value.destination, input_value.seed, input_value.lines)
    if output_value.file != expected:
        return result(False, f"the log is not saved as {expected}", file=output_value.file)
    target = Path(workspace) / expected
    if not target.is_file():
        return result(False, f"{expected} is not in the workspace")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if output_value.sha256 != digest:
        return result(False, "sha256 does not match the file's bytes", declared=output_value.sha256, actual=digest)
    entries = read_log(workspace, expected)
    if isinstance(entries, str):
        return result(False, entries)
    if len(entries) != input_value.lines or output_value.lines != input_value.lines:
        return result(False, f"the file holds {len(entries)} lines, not {input_value.lines}")
    for number, entry in enumerate(entries):
        if entry[0] != timestamp(number):
            return result(False, f"line {number + 1} is stamped {entry[0]}, not {timestamp(number)}")
    return result(True, f"{expected} holds {len(entries)} lines", sha256=digest)
