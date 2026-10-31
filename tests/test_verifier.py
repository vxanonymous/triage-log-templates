from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from slimconfig import build_output, plain_output

import verifier
from contract import TASKS, TOOLS, GenerateInput, MineInput, Task, Tool
from plugin import generate_log, mine_templates
from plugin.logs import TEMPLATES, incident

START = "2026-10-31T12:00:00Z"


# The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
def verify_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


def verify_output(tool: str, given: dict, made: dict, workspace: Path) -> dict:
    classes = TOOLS[Tool(tool)]
    return verifier.verify_output(tool, build_output(given, classes[0]), build_output(made, classes[1]), str(workspace))


def verify_task(task: str, arguments: dict, output: dict, workspace: Path) -> dict:
    given, made = TASKS[Task(task)]
    return verifier.verify_task(task, build_output(arguments, given), build_output(output, made), None, str(workspace))


def generated(workspace: Path, seed: int = 2, lines: int = 20_000) -> tuple[dict, dict]:
    given = {"seed": seed, "lines": lines, "destination": "logs"}
    return given, plain_output(generate_log(GenerateInput(**given), workspace))


def mined(workspace: Path, file: str, start: int, end: int, top: int = 200) -> tuple[dict, dict]:
    given = {"file": file, "start_line": start, "end_line": end, "top": top}
    return given, plain_output(mine_templates(build_output(given, MineInput), workspace))


def stamp(second: int) -> str:
    return f"2026-10-31T12:{second // 60:02d}:{second % 60:02d}Z"


# generate_log


@pytest.mark.parametrize("lines", [500, 20_000, 100_000])
def test_approves_a_generated_log(tmp_path: Path, lines: int) -> None:
    given, made = generated(tmp_path, lines=lines)
    assert verify_output("generate_log", given, made, tmp_path)["valid"] is True
    assert verify_task("generate-log", given, made, tmp_path)["valid"] is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"file": "logs/app-3-20000.log"}, "not saved as"),
        ({"sha256": "0" * 64}, "sha256"),
        ({"lines": 19_999}, "lines"),
    ],
)
def test_refuses_a_wrong_generate_output(tmp_path: Path, changes: dict, message: str) -> None:
    given, made = generated(tmp_path)
    verdict = verify_output("generate_log", given, made | changes, tmp_path)
    assert verdict["valid"] is False and message in verdict["message"]


def test_refuses_a_missing_or_tampered_log(tmp_path: Path) -> None:
    given, made = generated(tmp_path)
    target = tmp_path / made["file"]
    target.write_text(target.read_text() + "2026-11-01T00:00:00Z INFO gateway extra\n")
    assert "sha256" in verify_output("generate_log", given, made, tmp_path)["message"]
    target.unlink()
    assert "not in the workspace" in verify_output("generate_log", given, made, tmp_path)["message"]


def test_refuses_a_log_with_the_right_hash_but_wrong_content(tmp_path: Path) -> None:
    # A hand-written file whose declared hash is its own still has to be the requested log.
    given = {"seed": 1, "lines": 500, "destination": "logs"}
    (tmp_path / "logs").mkdir()
    target = tmp_path / "logs" / "app-1-500.log"
    target.write_text("".join(f"{stamp(n + 1)} INFO gateway hello\n" for n in range(500)))
    made = {"file": "logs/app-1-500.log", "lines": 500, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    assert "stamped" in verify_output("generate_log", given, made, tmp_path)["message"]
    target.write_text("".join(f"{stamp(n)} DEBUG gateway hello\n" for n in range(500)))
    made["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    assert "line 1 is not" in verify_output("generate_log", given, made, tmp_path)["message"]
    target.write_text("".join(f"{stamp(n)} INFO gateway hello\n" for n in range(499)))
    made["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    assert "499 lines" in verify_output("generate_log", given, made, tmp_path)["message"]


# mine_templates


@pytest.mark.parametrize(
    ("start", "end", "top"), [(1, 10_000, 200), (10_001, 20_000, 3), (1, 1, 1), (20_000, 20_000, 200)]
)
def test_approves_mined_templates(tmp_path: Path, start: int, end: int, top: int) -> None:
    _, log = generated(tmp_path)
    given, made = mined(tmp_path, log["file"], start, end, top)
    assert verify_output("mine_templates", given, made, tmp_path)["valid"] is True
    assert verify_task("mine-log-templates", given, made, tmp_path)["valid"] is True


def test_refuses_mined_templates_that_are_wrong(tmp_path: Path) -> None:
    _, log = generated(tmp_path)
    given, made = mined(tmp_path, log["file"], 1, 10_000)
    first, second = made["templates"][0], made["templates"][1]
    rest = made["templates"][2:]
    cases = {
        "missing": made | {"templates": made["templates"][1:]},
        "extra": made | {"templates": [*made["templates"], {"template": "INFO x y", "count": 1, "first_line": 1}]},
        "count": made | {"templates": [first | {"count": first["count"] + 1}, second, *rest]},
        "first_line": made | {"templates": [first | {"first_line": first["first_line"] + 1}, second, *rest]},
        "order": made | {"templates": [second, first, *rest]},
        "unmasked": made | {"templates": [first | {"template": first["template"] + " 7"}, second, *rest]},
        "distinct": made | {"distinct": made["distinct"] + 1},
        "lines": made | {"lines": 9_999},
        "echo": made | {"start_line": 2},
    }
    for name, output in cases.items():
        assert verify_output("mine_templates", given, output, tmp_path)["valid"] is False, name


def test_breaks_ties_by_template_text(tmp_path: Path) -> None:
    rows = [f"{stamp(0)} ERROR b x 1", f"{stamp(1)} ERROR a y 2", f"{stamp(2)} INFO c z"]
    (tmp_path / "tie.log").write_text("\n".join(rows) + "\n")
    given, made = mined(tmp_path, "tie.log", 1, 3, 2)
    assert [t["template"] for t in made["templates"]] == ["ERROR a y <NUM>", "ERROR b x <NUM>"]
    assert verify_output("mine_templates", given, made, tmp_path)["valid"] is True
    swapped = made | {"templates": made["templates"][::-1]}
    assert verify_output("mine_templates", given, swapped, tmp_path)["valid"] is False


def test_refuses_a_window_past_the_file_or_a_malformed_log(tmp_path: Path) -> None:
    (tmp_path / "ok.log").write_text(f"{START} INFO gateway hello\n")
    given = {"file": "ok.log", "start_line": 1, "end_line": 2, "top": 10}
    made = {"file": "ok.log", "start_line": 1, "end_line": 2, "lines": 2, "distinct": 1, "templates": []}
    assert "past the file" in verify_output("mine_templates", given, made, tmp_path)["message"]
    (tmp_path / "bad.log").write_text("no levels here\n")
    bad = given | {"file": "bad.log", "end_line": 1}
    assert (
        "not '<timestamp>"
        in verify_output("mine_templates", bad, made | {"file": "bad.log", "end_line": 1}, tmp_path)["message"]
    )
    (tmp_path / "bad.log").unlink()
    assert (
        "not in the workspace"
        in verify_output("mine_templates", bad, made | {"file": "bad.log", "end_line": 1}, tmp_path)["message"]
    )


def test_checks_what_the_types_cannot_say() -> None:
    good = {"file": "logs/a.log", "start_line": 1, "end_line": 10, "top": 200}
    assert verify_input("mine_templates", good)["valid"] is True
    assert verify_input("mine_templates", good | {"start_line": 10, "top": 1})["valid"] is True
    for bad in (
        {"start_line": 0},
        {"start_line": 11},
        {"top": 0},
        {"top": 201},
        {"file": "../a.log"},
        {"file": "a.txt"},
    ):
        assert verify_input("mine_templates", good | bad)["valid"] is False, bad
    generate = {"seed": 1, "lines": 500, "destination": "logs"}
    assert verify_input("generate_log", generate)["valid"] is True
    assert verify_input("generate_log", generate | {"lines": 100_000})["valid"] is True
    for bad in ({"lines": 499}, {"lines": 100_001}, {"destination": "/abs"}, {"destination": "../x"}):
        assert verify_input("generate_log", generate | bad)["valid"] is False, bad


# find-spiking-error


def spike(workspace: Path, seed: int = 2, lines: int = 20_000) -> tuple[dict, dict]:
    """What a correct agent submits: generate, mine both halves with top 200, take the largest ERROR increase."""
    _, log = generated(workspace, seed, lines)
    half = lines // 2
    _, first = mined(workspace, log["file"], 1, half)
    _, second = mined(workspace, log["file"], half + 1, lines)
    before = {t["template"]: t["count"] for t in first["templates"]}
    after = {t["template"]: t["count"] for t in second["templates"]}
    errors = [text for text in set(before) | set(after) if text.startswith("ERROR ")]
    best = min(errors, key=lambda text: (-(after.get(text, 0) - before.get(text, 0)), text))
    output = {
        "file": log["file"],
        "template": best,
        "first_half_count": before.get(best, 0),
        "second_half_count": after.get(best, 0),
    }
    return {"seed": seed, "lines": lines}, output


@pytest.mark.parametrize(("seed", "lines"), [(2, 20_000), (7, 2000), (4, 500)])
def test_approves_the_right_spike(tmp_path: Path, seed: int, lines: int) -> None:
    arguments, output = spike(tmp_path, seed, lines)
    planted, _ = incident(seed, lines)
    assert output["template"].startswith(f"ERROR {TEMPLATES[planted][1]} ")
    assert output["second_half_count"] > output["first_half_count"]
    verdict = verify_task("find-spiking-error", arguments, output, tmp_path)
    assert verdict["valid"] is True and verdict["score"] == 1.0


@pytest.mark.parametrize(
    ("changes", "failed"),
    [
        # A steady template is wrong, and the right template's counts do not match it.
        ({"template": 'ERROR notifier SMTP send failed for recipient "<STR>" with code <NUM>'}, ["template"]),
        ({"first_half_count": 0}, ["first_half_count"]),
        ({"second_half_count": 1}, ["second_half_count"]),
        ({"file": "logs/app-2-20000.txt"}, ["file"]),
    ],
)
def test_refuses_a_wrong_spike_and_scores_what_is_right(tmp_path: Path, changes: dict, failed: list) -> None:
    arguments, output = spike(tmp_path)
    verdict = verify_task("find-spiking-error", arguments, output | changes, tmp_path)
    assert verdict["valid"] is False and verdict["details"]["failed"] == failed
    assert verdict["score"] == (4 - len(failed)) / 4


def test_refuses_a_spike_from_another_log_or_none(tmp_path: Path) -> None:
    arguments, output = spike(tmp_path)
    assert verify_task("find-spiking-error", arguments | {"seed": 3}, output, tmp_path)["valid"] is False
    (tmp_path / output["file"]).unlink()
    verdict = verify_task("find-spiking-error", arguments, output, tmp_path)
    assert "not in the workspace" in verdict["message"] and verdict["score"] == 0.0


def test_a_tie_accepts_either_template(tmp_path: Path) -> None:
    # Lines 1..250 hold no errors; lines 251..500 hold two ERROR templates three times each.
    rows = [f"{stamp(n)} INFO gateway ok" for n in range(500)]
    for n in (300, 310, 320):
        rows[n] = f"{stamp(n)} ERROR a broke {n}"
        rows[n + 1] = f"{stamp(n + 1)} ERROR b broke {n}"
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "app-0-500.log").write_text("\n".join(rows) + "\n")
    arguments = {"seed": 0, "lines": 500}
    for template in ("ERROR a broke <NUM>", "ERROR b broke <NUM>"):
        submitted = {"file": "logs/app-0-500.log", "template": template, "first_half_count": 0, "second_half_count": 3}
        assert verify_task("find-spiking-error", arguments, submitted, tmp_path)["valid"] is True
    wrong = {"file": "logs/app-0-500.log", "template": "INFO gateway ok", "first_half_count": 0, "second_half_count": 3}
    verdict = verify_task("find-spiking-error", arguments, wrong, tmp_path)
    assert verdict["details"]["failed"] == ["template"] and verdict["score"] == 0.75
