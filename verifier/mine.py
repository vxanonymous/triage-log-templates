"""mine_templates' checks: template counts recomputed from the file with the README's masking rules."""

from .checks import MAX_TOP, path_problem, read_log, result, window_counts


def verify_input(value):
    problem = path_problem(value.file, ".log")
    if problem:
        return result(False, problem)
    if not 1 <= value.top <= MAX_TOP:
        return result(False, f"top must be between 1 and {MAX_TOP}")
    if not 1 <= value.start_line <= value.end_line:
        return result(False, "need 1 <= start_line <= end_line")
    return result(True, "input is valid")


def mining_problems(input_value, output_value, entries):
    """Every way ``output_value`` differs from the window's true templates; empty when it matches."""
    if input_value.end_line > len(entries):
        return [f"end_line {input_value.end_line} is past the file's last line, {len(entries)}"]
    counts, first = window_counts(entries, input_value.start_line, input_value.end_line)
    problems = []
    asked = (input_value.file, input_value.start_line, input_value.end_line)
    echoed = (output_value.file, output_value.start_line, output_value.end_line)
    if echoed != asked:
        problems.append("file, start_line or end_line is not the one asked for")
    size = input_value.end_line - input_value.start_line + 1
    if output_value.lines != size:
        problems.append(f"lines is {output_value.lines}, but the window holds {size}")
    if output_value.distinct != len(counts):
        problems.append(f"distinct is {output_value.distinct}, but the window holds {len(counts)} templates")
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: input_value.top]
    expected = [(text, count, first[text]) for text, count in ranked]
    given = [(item.template, item.count, item.first_line) for item in output_value.templates]
    if len(given) != len(expected):
        problems.append(f"{len(given)} templates are listed, not {len(expected)}")
    for place, (want, got) in enumerate(zip(expected, given), start=1):
        if got[0] != want[0]:
            problems.append(f"template {place} is {got[0]!r}, not {want[0]!r}")
        elif got[1] != want[1]:
            problems.append(f"{want[0]!r} count is {got[1]}, not {want[1]}")
        elif got[2] != want[2]:
            problems.append(f"{want[0]!r} first_line is {got[2]}, not {want[2]}")
    return problems


def verify_output(input_value, output_value, workspace):
    entries = read_log(workspace, input_value.file)
    if isinstance(entries, str):
        return result(False, entries)
    problems = mining_problems(input_value, output_value, entries)
    if problems:
        return result(False, problems[0], problems=problems)
    return result(True, f"{len(output_value.templates)} templates match the window's true counts")
