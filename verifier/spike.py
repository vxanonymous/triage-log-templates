"""find-spiking-error's check: the submitted template and counts, against templates mined from the seed's log."""

from .checks import read_log, result, window_counts
from .generate import expected_file


def verify_task(arguments, output, reference, workspace):
    """``output``: a contract SpikeOutput for the log generated from ``arguments``' seed and line count."""
    expected = expected_file("logs", arguments.seed, arguments.lines)
    checks = {"file": output.file == expected}
    entries = read_log(workspace, expected)
    if isinstance(entries, str):
        return result(False, entries, score=0.0, failed=["file", "template", "first_half_count", "second_half_count"])
    if len(entries) != arguments.lines:
        return result(False, f"{expected} holds {len(entries)} lines, not {arguments.lines}", score=0.0)
    half = arguments.lines // 2
    first, _ = window_counts(entries, 1, half)
    second, _ = window_counts(entries, half + 1, arguments.lines)
    errors = sorted(text for text in set(first) | set(second) if text.split(" ", 1)[0] == "ERROR")
    if not errors:
        return result(False, "the log has no ERROR lines, so nothing spiked", score=0.0)
    growth = {text: second.get(text, 0) - first.get(text, 0) for text in errors}
    most = max(growth.values())
    spiking = [text for text in errors if growth[text] == most]
    checks["template"] = output.template in spiking
    # Counts are judged for the submitted template when it is right, and for the right answer when it is not.
    judged = [output.template] if output.template in spiking else spiking
    checks["first_half_count"] = any(output.first_half_count == first.get(text, 0) for text in judged)
    checks["second_half_count"] = any(output.second_half_count == second.get(text, 0) for text in judged)
    failed = [name for name, passed in checks.items() if not passed]
    details = {
        "spiking": spiking,
        "first_half_count": first.get(spiking[0], 0),
        "second_half_count": second.get(spiking[0], 0),
        "increase": most,
        "failed": failed,
    }
    score = (len(checks) - len(failed)) / len(checks)
    if failed:
        return result(False, f"wrong {', '.join(failed)}", score=score, **details)
    return result(True, f"{output.template!r} grew by {most} lines", **details)
