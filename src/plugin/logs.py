"""generate_log: a seeded application log with one planted error spike, written into the workspace."""

import hashlib
import random
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from contract import GenerateInput, GenerateOutput

MIN_LINES, MAX_LINES = 500, 100_000
START = 1_793_448_000  # 2026-10-31T12:00:00Z, so every file shares one clock
WORDS = ["alpha", "bravo", "cart", "delta", "echo", "invoice", "kilo", "lima", "promo", "quota", "refund", "zulu"]
# The planted template's weight before and after the incident starts, against a total weight of 1000.
QUIET_WEIGHT, LOUD_WEIGHT = 1.5, 100.0


def _int(rng: random.Random) -> str:
    return str(rng.randint(1, 999_999))


def _ms(rng: random.Random) -> str:
    return f"{rng.randint(1, 9000)}ms"


def _decimal(rng: random.Random) -> str:
    return f"{rng.uniform(0, 1000):.2f}"


def _ip(rng: random.Random) -> str:
    return f"10.{rng.randrange(256)}.{rng.randrange(256)}.{rng.randrange(1, 255)}"


def _ip_port(rng: random.Random) -> str:
    return f"{_ip(rng)}:{rng.randint(1024, 65535)}"


def _uuid(rng: random.Random) -> str:
    raw = f"{rng.getrandbits(128):032x}"
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def _hex8(rng: random.Random) -> str:
    # A digit up front, so the run is always masked as <HEX>.
    return f"{rng.randrange(10)}{rng.getrandbits(36):09x}"


def _hex0x(rng: random.Random) -> str:
    return f"0x{rng.getrandbits(16):x}"


def _quoted(rng: random.Random) -> str:
    return f'"{rng.choice(WORDS)} {rng.choice(WORDS)}"'


def _path(rng: random.Random) -> str:
    return f"/var/lib/billing/batch-{rng.randint(1, 999)}/part-{rng.randint(1, 99)}.parquet"


FILLERS: dict[str, Callable[[random.Random], str]] = {
    "int": _int,
    "ms": _ms,
    "dec": _decimal,
    "ip": _ip,
    "ipport": _ip_port,
    "uuid": _uuid,
    "hex8": _hex8,
    "hex0x": _hex0x,
    "str": _quoted,
    "path": _path,
}
# (level, service, message with {filler} fields, weight out of 1000). One service per message, so every
# message template masks to exactly one line template.
TEMPLATES = [
    ("INFO", "gateway", "GET /api/orders/{int} returned 200 in {ms}", 180),
    ("INFO", "gateway", "Accepted connection from {ipport}", 110),
    ("INFO", "auth", "User {int} logged in from {ip} session {uuid}", 80),
    ("INFO", "auth", "Token refreshed for user {int} expires in {int} seconds", 60),
    ("INFO", "orders", "Order {uuid} created with {int} items total {dec}", 70),
    ("INFO", "inventory", "Reserved {int} units of sku {hex8} in warehouse {int}", 60),
    ("INFO", "search", "Query {str} returned {int} hits in {ms}", 80),
    ("INFO", "payments", 'Charge {uuid} captured amount {dec} currency "USD"', 50),
    ("INFO", "notifier", "Sent email to user {int} with template {str}", 40),
    ("INFO", "billing", "Invoice {int} generated for account {hex0x}", 35),
    ("WARN", "gateway", "Slow upstream {ipport} took {ms}", 40),
    ("WARN", "auth", "Failed login for user {str} from {ip}", 35),
    ("WARN", "search", "Cache miss ratio {dec} above threshold {dec}", 25),
    ("WARN", "inventory", "Stock for sku {hex8} below {int} units", 30),
    ("ERROR", "orders", "Database timeout after {ms} on shard {int} query {hex0x}", 15),
    ("ERROR", "payments", "Payment provider returned 502 for charge {uuid}", 15),
    ("ERROR", "auth", "Token signature invalid for session {uuid} from {ip}", 15),
    ("ERROR", "gateway", "Upstream {ipport} refused connection on retry {int} of 5", 15),
    ("ERROR", "billing", "Failed to write {path} with disk usage {dec} percent", 15),
    ("ERROR", "notifier", "SMTP send failed for recipient {str} with code {int}", 15),
    ("ERROR", "inventory", "Lock wait exceeded on row {int} trace {hex8}", 15),
]
ERRORS = [index for index, template in enumerate(TEMPLATES) if template[0] == "ERROR"]


def safe_folder(destination: str) -> Path:
    path = Path(destination)
    if not destination.strip() or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"destination {destination!r} must be a folder inside the plugin workspace")
    return path


def log_name(seed: int, lines: int) -> str:
    return f"app-{seed}-{lines}.log"


def _timestamp(second: int) -> str:
    return datetime.fromtimestamp(START + second, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fill(message: str, rng: random.Random) -> str:
    parts = message.split("{")
    out = [parts[0]]
    for part in parts[1:]:
        name, rest = part.split("}", 1)
        out.append(FILLERS[name](rng) + rest)
    return "".join(out)


def incident(seed: int, lines: int) -> tuple[int, int]:
    """The planted ERROR template's index and the 0-based line where its spike starts."""
    rng = random.Random(seed)
    planted = rng.choice(ERRORS)
    onset = rng.randint(lines // 2, (lines * 3) // 5)
    return planted, onset


def log_lines(seed: int, lines: int) -> list[str]:
    planted, onset = incident(seed, lines)
    rng = random.Random(f"{seed}-{lines}")
    before = [float(template[3]) for template in TEMPLATES]
    before[planted] = QUIET_WEIGHT
    after = list(before)
    after[planted] = LOUD_WEIGHT
    # The spike takes its share from the busiest INFO template, so the other templates keep their rates.
    after[0] -= LOUD_WEIGHT - TEMPLATES[planted][3]
    before[0] += TEMPLATES[planted][3] - QUIET_WEIGHT
    indexes = range(len(TEMPLATES))
    out = []
    for line in range(lines):
        chosen = rng.choices(indexes, after if line >= onset else before)[0]
        level, service, message, _ = TEMPLATES[chosen]
        out.append(f"{_timestamp(line)} {level} {service} {_fill(message, rng)}")
    return out


def generate_log(given: GenerateInput, workspace: Path) -> GenerateOutput:
    if not MIN_LINES <= given.lines <= MAX_LINES:
        raise ValueError(f"lines must be between {MIN_LINES} and {MAX_LINES}, got {given.lines}")
    relative = safe_folder(given.destination) / log_name(given.seed, given.lines)
    data = ("\n".join(log_lines(given.seed, given.lines)) + "\n").encode("utf-8")
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return GenerateOutput(file=relative.as_posix(), lines=given.lines, sha256=hashlib.sha256(data).hexdigest())
