from pathlib import Path

import pytest

from contract import GenerateInput, MineInput
from plugin import generate_log, mine_templates
from plugin.logs import TEMPLATES, incident
from plugin.mine import mask, template_of


def test_the_same_seed_gives_the_same_bytes(tmp_path: Path) -> None:
    first = generate_log(GenerateInput(seed=7, lines=2000, destination="logs"), tmp_path)
    data = (tmp_path / first.file).read_bytes()
    second = generate_log(GenerateInput(seed=7, lines=2000, destination="logs"), tmp_path)
    assert first == second and (tmp_path / second.file).read_bytes() == data
    assert first.file == "logs/app-7-2000.log"
    lines = data.decode().splitlines()
    assert len(lines) == 2000 and lines[0].startswith("2026-10-31T12:00:00Z ")
    assert lines[-1].startswith("2026-10-31T12:33:19Z ")
    other = generate_log(GenerateInput(seed=8, lines=2000, destination="logs"), tmp_path)
    assert other.sha256 != first.sha256


@pytest.mark.parametrize(
    ("lines", "destination"),
    [(499, "logs"), (100_001, "logs"), (2000, "../out"), (2000, "/tmp/x"), (2000, " ")],
)
def test_refuses_bad_generate_inputs(tmp_path: Path, lines: int, destination: str) -> None:
    with pytest.raises(ValueError):
        generate_log(GenerateInput(seed=1, lines=lines, destination=destination), tmp_path)


@pytest.mark.parametrize(
    ("message", "masked"),
    [
        ('Query "promo cart" returned 42 hits in 18ms', 'Query "<STR>" returned <NUM> hits in <NUM>'),
        (
            "Upstream 10.4.7.19:5432 refused connection on retry 3 of 5",
            "Upstream <IP> refused connection on retry <NUM> of <NUM>",
        ),
        ("session 123e4567-e89b-12d3-a456-426614174000 from 10.0.0.1", "session <UUID> from <IP>"),
        ("account 0x1f3a sku 3abcdef01 word deadbeef", "account <HEX> sku <HEX> word deadbeef"),
        ("Failed to write /var/x/batch-7/part-2.parquet usage 81.50", "Failed to write <NUM> usage <NUM>"),
        ('mixed "a 1"   spaced  out', 'mixed "<STR>" spaced out'),
        ("version 1.2.3.4.5 is not an address", "version <NUM> is not an address"),
    ],
)
def test_masks_in_the_documented_order(message: str, masked: str) -> None:
    assert mask(message) == masked


def test_every_generated_message_masks_to_its_own_template(tmp_path: Path) -> None:
    log = generate_log(GenerateInput(seed=3, lines=20_000, destination="logs"), tmp_path)
    templates = {template_of(line) for line in (tmp_path / log.file).read_text().splitlines()}
    assert None not in templates and len(templates) == len(TEMPLATES)


def test_the_planted_error_spikes_after_its_onset(tmp_path: Path) -> None:
    log = generate_log(GenerateInput(seed=5, lines=20_000, destination="logs"), tmp_path)
    planted, onset = incident(5, 20_000)
    assert TEMPLATES[planted][0] == "ERROR" and 10_000 <= onset <= 12_000
    first = mine_templates(MineInput(file=log.file, start_line=1, end_line=10_000, top=200), tmp_path)
    second = mine_templates(MineInput(file=log.file, start_line=10_001, end_line=20_000, top=200), tmp_path)
    service = TEMPLATES[planted][1]
    before = next(t.count for t in first.templates if t.template.startswith(f"ERROR {service} "))
    after = next(t.count for t in second.templates if t.template.startswith(f"ERROR {service} "))
    assert after > 5 * before


def test_mines_a_window_in_order(tmp_path: Path) -> None:
    log = generate_log(GenerateInput(seed=1, lines=2000, destination="logs"), tmp_path)
    found = mine_templates(MineInput(file=log.file, start_line=11, end_line=500, top=5), tmp_path)
    assert found.lines == 490 and len(found.templates) == 5 and found.distinct >= 5
    keys = [(-t.count, t.template) for t in found.templates]
    assert keys == sorted(keys)
    assert all(11 <= t.first_line <= 500 for t in found.templates)
    one = mine_templates(MineInput(file=log.file, start_line=2000, end_line=2000, top=200), tmp_path)
    assert one.lines == 1 and one.distinct == 1 and one.templates[0].count == 1 and one.templates[0].first_line == 2000


@pytest.mark.parametrize(
    ("start", "end", "top"),
    [(0, 10, 10), (5, 4, 10), (1, 2001, 10), (1, 10, 0), (1, 10, 201)],
)
def test_refuses_bad_windows(tmp_path: Path, start: int, end: int, top: int) -> None:
    log = generate_log(GenerateInput(seed=1, lines=2000, destination="logs"), tmp_path)
    with pytest.raises(ValueError):
        mine_templates(MineInput(file=log.file, start_line=start, end_line=end, top=top), tmp_path)


def test_refuses_a_missing_foreign_or_malformed_file(tmp_path: Path) -> None:
    window = {"start_line": 1, "end_line": 1, "top": 10}
    with pytest.raises(FileNotFoundError):
        mine_templates(MineInput(file="logs/none.log", **window), tmp_path)
    (tmp_path / "other.txt").write_text("x\n")
    with pytest.raises(ValueError):
        mine_templates(MineInput(file="other.txt", **window), tmp_path)
    with pytest.raises(ValueError):
        mine_templates(MineInput(file="../outside.log", **window), tmp_path)
    (tmp_path / "bad.log").write_text("2026-10-31T12:00:00Z DEBUG svc hello\n")
    with pytest.raises(ValueError):
        mine_templates(MineInput(file="bad.log", **window), tmp_path)
