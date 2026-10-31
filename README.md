# Triage Log Templates

A `nanoagent.plugin/v0001` plugin for incident triage. It writes a seeded
application log with one planted error spike, then collapses any window of
the log into message templates by masking the parts of each message that
change from line to line. Counting templates per window lets a triage agent
see which message pattern took off during an incident without reading raw
lines.

## Tools

| Tool | Does | Code |
|---|---|---|
| `generate_log` | Writes the log for a seed and line count to `<destination>/app-<seed>-<lines>.log` and returns its path, line count and SHA-256 | `src/plugin/logs.py` |
| `mine_templates` | Masks every line from `start_line` to `end_line`, counts each template and returns the `top` most frequent, with each one's first line | `src/plugin/mine.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `generate-log` | Generates a seeded application log | `tool`, with `generate_log` |
| `mine-log-templates` | Counts the templates in a window of a log | `tool`, with `mine_templates` |
| `find-spiking-error` | Finds the ERROR template whose count grew the most from the first half of the log to the second | `agent`, with `generate_log` and `mine_templates` |

Each line is `<timestamp> <LEVEL> <service> <message>`, one line per second
from `2026-10-31T12:00:00Z`, with LEVEL one of INFO, WARN and ERROR, eight
services and 21 message templates. The seed picks one of the seven ERROR
templates: it stays rare until a line the seed picks between 50% and 60% of
the way through the file, then becomes frequent. The other ERROR templates
keep a steady rate. The same seed and line count always give the same bytes.

### Masking rules

A line's template is `LEVEL service masked-message`. The message is masked
with these rules, in this order:

1. Every double-quoted string becomes `"<STR>"`.
2. Every UUID (`8-4-4-4-12` hex digits) becomes `<UUID>`.
3. Every IPv4 address, with or without `:port`, becomes `<IP>`.
4. Every `0x`-prefixed hex number, and every standalone run of 8 or more hex
   characters holding at least one digit, becomes `<HEX>`.
5. The message is split on whitespace, every token that still holds a digit
   becomes `<NUM>`, and the tokens are joined with single spaces.

So `Upstream 10.4.7.19:5432 refused connection on retry 3 of 5` becomes
`Upstream <IP> refused connection on retry <NUM> of <NUM>`, and
`Query "promo cart" returned 42 hits in 18ms` becomes
`Query "<STR>" returned <NUM> hits in <NUM>`. Generated logs never hold more
than 21 distinct templates, so `top` 200 always returns every one.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none here)
├── src/plugin/      # the MCP server (__main__.py, its IMPLEMENTATIONS table) and the tools
├── tests/
├── ui/              # outputs are drawn from their JSON Schema
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier, one module per tool, and spike.py for find-spiking-error
```

`verifier/` imports only the standard library and `contract`. It reads the
log back from the workspace, applies its own copy of the masking rules and
recounts every template, then checks:

- `generate_log`: the file is at `<destination>/app-<seed>-<lines>.log`, its
  SHA-256 is the declared one, it holds exactly the requested lines, every
  line has a level and a service, and line `n` is stamped `n - 1` seconds
  after the start.
- `mine_templates`: the window is inside the file, the echoed window, line
  count and distinct count are exact, and the listed templates are exactly
  the window's top ones, with exact counts and first lines, in order.
- `find-spiking-error`: the file is the seed's log, the template has the
  largest increase among ERROR templates (any of them on a tie), and both
  half counts are exact. The score is the share of these four checks that
  pass.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`.
Logs are written there; `mine_templates` reads a log by its path inside it.
