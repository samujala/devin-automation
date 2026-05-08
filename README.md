# Devin Auto-Remediation for Apache Superset

An event-driven automation system that uses [Devin](https://devin.ai) to remediate static analysis findings in a fork of Apache Superset — autonomously opening reviewable pull requests and reporting on its work through a live dashboard.

## Why this exists

Every sufficiently large Python codebase accumulates a long tail of small, defensible-but-tedious code quality issues: deprecated API calls, annotation syntax that should have been modernized years ago, timezone-naive datetimes waiting to cause production bugs. Engineers know exactly how to fix each one. Nobody has time to do it.

This system treats that long tail as a work queue. The scanner discovers 113 violations of two ruff rules across Superset, groups them into 9 logically scoped GitHub issues, and labels each one `auto-remediable`. The orchestrator watches for that label, builds a rule-specific prompt, and hands each issue to Devin — which clones the fork, applies the fix, runs the tests, and opens a reviewable PR. The result: approximately 7 PRs authored autonomously, each scoped to a directory or file so a human reviewer can evaluate it in minutes rather than hours.

The dashboard gives a live view of session outcomes, throughput, and failure modes — so you know at a glance whether the automation is healthy or stuck.

## Architecture

```
   GitHub Actions cron (or manual run)
              │
              ▼
   ┌────────────────────────────┐
   │      scanner/              │
   │  • Runs ruff on Superset   │
   │  • Groups findings into    │
   │    9 logical batches       │
   │  • Files GitHub issues     │
   └────────────┬───────────────┘
                │  GitHub issues
                │  with `auto-remediable` label
                ▼
   ┌────────────────────────────┐         ┌──────────────────────┐
   │      orchestrator/         │         │      Devin API       │
   │  • Polls GitHub for new    │ ──────▶ │  • Spawns session    │
   │    auto-remediable issues  │         │  • Clones fork       │
   │  • Builds prompt from      │         │  • Edits + tests     │
   │    rule-specific template  │ ◀────── │  • Opens PR          │
   │  • Caps 3 concurrent       │   poll  └──────────────────────┘
   │  • Records lifecycle       │
   └────────────┬───────────────┘
                │
                │ writes
                ▼
       SQLite (data/findings.db)
                │
                │ reads
                ▼
   ┌────────────────────────────┐         ┌──────────────────────┐
   │      api/  (FastAPI)       │ ──────▶ │   dashboard/         │
   │  • /api/metrics            │  HTTP   │   (Next.js + shadcn) │
   │  • /api/sessions/...       │  poll   │   • Live KPIs        │
   └────────────────────────────┘  every  │   • Throughput chart │
                                    5s    │   • Failure analysis │
                                          └──────────────────────┘
```

**The trigger.** The scanner runs on a schedule (or manually via `python -m scanner.scan`) and produces one GitHub issue per batch, labeled `auto-remediable`. The orchestrator's trigger is that label — surfaced via polling for simplicity. In production this would upgrade to a webhook listener or Devin's native scheduled-tasks feature, reducing the polling latency to near-zero without any architectural rework.

**The autonomous worker.** The orchestrator is intentionally thin. It builds a structured prompt from a rule-specific template, calls Devin's API to create a session, and polls for completion. The actual remediation work — cloning the repo, editing files, running tests, opening the PR — happens in Devin's environment. Session completion is detected via the `status_enum: blocked` field in Devin's API response (not the `status` field, which remains `"running"` throughout). The orchestrator caps concurrency at 3 sessions and enforces a 30-minute per-session timeout.

**The observability layer.** All state lives in SQLite across three tables: `batches` (one row per scanner run), `devin_sessions` (one row per Devin session), and `session_events` (append-only lifecycle log). The FastAPI layer reads only — no writes — and exposes five endpoints the dashboard polls every 5 seconds. Because session events are append-only, the database is replayable: on restart, the orchestrator queries for any sessions still marked in-progress and resumes polling them without losing state.

## The remediation portfolio

| # | Batch key | Rule | Scope | Type |
|---|---|---|---|---|
| 1 | `up007_utils` | UP007 | `superset/utils/` | Scoped |
| 2 | `up007_commands` | UP007 | `superset/commands/` | Scoped |
| 3 | `up007_models_daos` | UP007 | `superset/models/`, `superset/daos/` | Scoped |
| 4 | `up007_long_tail` | UP007 | All remaining UP007 files | Catch-all |
| 5 | `dtz003_cache_py` | DTZ003 | `superset/utils/cache.py` | Scoped |
| 6 | `dtz003_dates_py` | DTZ003 | `superset/utils/dates.py` | Scoped |
| 7 | `dtz003_log_py` | DTZ003 | `superset/daos/log.py` | Scoped |
| 8 | `dtz003_execute_py` | DTZ003 | `superset/commands/report/execute.py` | Scoped |
| 9 | `dtz003_other` | DTZ003 | All remaining DTZ003 files | Catch-all |

Batches are data, not code. Adding a 10th batch is one entry in [`scanner/batches.py`](scanner/batches.py).

## Why these specific issues

The rule selection was deliberate. We chose rules with real, actionable findings in Superset where the fix is either mechanical or well-scoped enough to specify in a prompt.

- **Migrations excluded** — `superset/migrations/` is exempt by the Superset team's own convention. The scanner respects that policy; Devin never touches migration files.
- **UP007 is theoretically autofix-able** — ruff can rewrite `Optional[X]` → `X | None` in one command. But a 92-file PR is unreviewable, so we batch by directory, making each PR small enough to approve in a code review slot.
- **DTZ003 requires reasoning** — replacing `datetime.utcnow()` with `datetime.now(tz=timezone.utc)` is safe at some call sites and wrong at others. The prompt template encodes the reasoning explicitly (see next section).
- **`dtz003_execute_py` is a designed partial-success case** — Devin should fix the safe sites, comment on the issue about sites that write to tz-naive SQLAlchemy columns, and stop. The dashboard will show this as a partial outcome. This tests whether the system handles nuance correctly, not just happy paths.

## The prompt template — why it matters

The prompt template is the single most important piece of code in this system. It is the *policy layer* that turns "here is a finding" into "here is how a senior engineer would fix it without breaking things."

The DTZ003 template's key passage is the reasoning it asks Devin to apply before touching any call site ([`orchestrator/prompt_builder.py`](orchestrator/prompt_builder.py)):

```
4. For each call site, BEFORE making the change, determine how the
   returned datetime is used:

   a. Is it stored in a SQLAlchemy model field? Check the column
      definition. If the column is declared as `DateTime` without
      `timezone=True`, the change can break the write — DO NOT modify
      that site. Instead, comment on the issue explaining which line(s)
      need human review and skip them.

   b. Is it compared to or arithmetic'd with other datetime values?
      Check whether those other values are tz-aware or naive. A
      tz-aware vs. naive comparison raises TypeError at runtime.

   c. Is it returned from a function whose callers depend on a naive
      datetime?
```

This reasoning does not live in Devin's base capabilities — it lives in the template, where it can be reviewed, versioned, and iterated on like any other code. The PR body template is similarly structured: it requires Devin to list both the sites changed and the sites intentionally skipped, with justifications.

*"The prompt template is the customer-customizable surface. In a real engagement, this is where Forward Deployed work concentrates — encoding the customer's coding standards, their review conventions, and which fixes their team trusts to autopilot vs. route to humans."*

## Quick start

### Prerequisites

- Docker + Docker Compose
- A GitHub fine-grained PAT with `Issues: Read+Write` on your fork (for the scanner)
- A Devin API key (for the orchestrator)
- Python 3.11+ (for running the scanner/orchestrator outside Docker)
- Node 20+ (only if developing the dashboard outside Docker)

### Setup

1. Fork [apache/superset](https://github.com/apache/superset) and clone it as a sibling directory:

```bash
mkdir cognition && cd cognition
git clone <your-fork-url> superset
git clone <this-repo> automation
cd automation
```

2. Configure environment:

```bash
cp .env.example .env
# edit .env and fill in:
# GITHUB_TOKEN, GITHUB_REPO, DEVIN_API_KEY
```

3. Install Python dependencies (for scanner + orchestrator):

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Step 1 — File the issues

Run the scanner to populate your fork with 9 auto-remediable issues:

```bash
python -m scanner.scan --superset-path ../superset
```

You will see 9 issues filed in your fork's Issues tab.

### Step 2 — Spin up the dashboard

```bash
docker compose up --build
```

Dashboard at http://localhost:3000. Initially empty — that is expected.

### Step 3 — Run the orchestrator

In a separate terminal:

```bash
# Smoke test on one batch
python -m orchestrator.run --only-batch dtz003_dates_py

# Or process all queued batches
python -m orchestrator.run
```

Watch the dashboard fill in as Devin opens PRs.

## Operational details

**Concurrency and timeouts.** The orchestrator runs at most 3 Devin sessions concurrently (`MAX_CONCURRENT_SESSIONS=3`). Each session has a 30-minute wall-clock timeout (`SESSION_TIMEOUT_SECONDS=1800`). Both are configurable via `.env`.

**Idempotency.** Re-running the scanner on an unchanged codebase produces the same batch fingerprints and skips already-filed issues. Re-running the orchestrator on a batch that already has an in-progress session resumes polling the existing session — it does not spawn a duplicate.

**Dry-run mode.** Both the scanner (`--dry-run`) and the orchestrator (`--dry-run`) support a preview mode that logs what would happen without making API calls or writing to the database. The orchestrator also supports `--print-prompts` to print the rendered Devin prompt for each pending batch.

**Logging.** The orchestrator emits structured single-line JSON to stdout for every lifecycle event: session creation, poll results, terminal detection, outcome recording. Pipe to `jq` for filtering or forward to any log aggregator.

**State recovery.** On restart, the orchestrator queries SQLite for any sessions still marked in-progress and resumes polling them. No state is lost across restarts.

**Diagnosing stuck sessions.** `scripts/backfill_stuck_sessions.py` re-polls all non-terminal sessions and finalizes any that have since completed — useful after a crash or a long pause.

## Repository layout

```
automation/
├── scanner/             # Finds violations, files GitHub issues
├── orchestrator/        # Manages Devin session lifecycle
├── api/                 # FastAPI read-only metrics service
├── dashboard/           # Next.js dashboard (port 3000)
├── data/                # SQLite database
├── scripts/             # Diagnostic + backfill utilities
├── docs/screenshots/    # Demo images for this README
├── docker-compose.yml
├── pyproject.toml       # Python project config
└── .env.example
```

## What I would extend in a real customer engagement

- Replace GitHub polling with webhooks via a deployed FastAPI endpoint — eliminates the polling latency and reduces API quota usage
- Evaluate Devin's native scheduled-tasks feature as the trigger; the orchestrator shrinks to a "policy and observability" layer rather than a session manager
- Add CI gate integration — only auto-remediate when CI was green on master; annotate the generated PR with a `[devin]` label for bulk filtering in the review queue
- Multi-rule fan-out — same orchestrator, per-customer allow-lists of rule codes and excluded paths; each customer gets a different `batches.py` and prompt templates
- Slack digest — daily summary of "Devin remediated N issues, M still need human review," linked directly to the open PRs
- Re-trigger UI in the dashboard — engineers can re-queue a failed batch with a tweaked prompt without touching the CLI

*"In a real deployment, the work concentrates on the prompt templates and the allow-list — these are the customer-specific governance surface. The plumbing (orchestrator, dashboard, observability) generalizes."*

## License

Apache 2.0 — consistent with the Apache Superset fork this system targets.

**Contact:** Someswar Amujala — someswar.amujala@gmail.com
