# Discovery (A2A) — demo runbook

> Purpose: exact, **verified** commands to record the capstone video for the two-agent
> job-discovery feature. Every command here has been run against the live source.
> Narrative/script lives elsewhere (NotebookLM); this is the "what to type" sheet.
> Companion: design in [ARCHITECTURE.md §15](ARCHITECTURE.md).

## The 30-second story (what the video shows)
A **stateless Scout** fetches live jobs through a **real MCP server**; a **stateful Primary**
evaluates each against the user's preferences + ledger and refines the search across a
**bounded loop** — typed `EvaluationDiff` messages between two decoupled agents, no secrets.

## 0. One-time setup
```bash
cd /workspaces/career-engine
pip install -e '.[dev]'      # installs mcp==1.28.1 among others
make check                   # ruff + mypy --strict + pytest → all green
```

## 1. Prove the MCP server is real and separate-process
The server speaks MCP over stdio. Show it exists and lists its two tools:
```bash
python - <<'PY'
import asyncio
from discovery.mcp_server import mcp
tools = asyncio.run(mcp.list_tools())
print("MCP server:", mcp.name)
for t in tools:
    print(" tool:", t.name, "—", (t.description or "").splitlines()[0])
PY
```
Expected:
```
MCP server: career-engine-jobs
 tool: search_jobs — Search a live job board and return normalised postings.
 tool: fetch_jd — Fetch the full plain-text job description at a posting URL (SSRF-guarded).
```
To show it running as its own process (optional, for the "separate process" beat):
```bash
python -m discovery.mcp_server      # blocks, serving MCP over stdio (Ctrl-C to stop)
```

## 2. Run the two-agent discovery loop (the money shot)
Runs the live Scout ⇄ Primary loop end-to-end and prints ranked matches with a rationale.
Works **with no key** (deterministic heuristic evaluator); with a BYOK Gemini key it uses
the Pro-tier `ModelEvaluator` for real reasoning.

```bash
python main.py discover --count 4 --max-iterations 3
```
Expected shape (companies/titles vary — it's a live source):
```
CareerEngine — job discovery (BYOK mode) for <user>
Targets: Fractional Technology Leadership, Consulting, Principal Engineer
============================================================
Discovery finished in 3 iteration(s): 3 accepted · 1 for review · 0 hard-rejected.

✅ ACCEPTED (strong matches):
  1. [ACCEPTED] Senior AI Engineer — Lemon.io
     full_time · remote · Northern America, LATAM, Europe, APAC
     https://remotive.com/remote-jobs/software-development/senior-ai-engineer-...
     → Matches your priorities: startup.
  ...
🟡 FOR REVIEW (soft matches):
  1. [SOFT_REJECT] Copywriter — Coalition Technologies
     → No explicit match to your target roles / nice-to-haves; kept for review.

Persisted 3 new accepted job(s) to your ledger (idempotent).
```

### For a real-reasoning capture (recommended for the video)
Set a BYOK Gemini key so the Primary uses `gemini-2.5-pro` and the rationales read
like genuine fit analysis rather than keyword hits. **Never paste the key in code or chat** —
export it in the shell only:
```bash
export DEV_USER_ID=demo
export DEV_GEMINI_KEY=***your-key***      # shell only; not committed, not logged
python main.py discover --count 4
```

## 3. Show idempotency (nice "it remembers" beat)
With `--firestore` (needs GCP creds), a second run hard-rejects already-seen jobs:
```bash
python main.py discover --count 4 --firestore   # run once → persists
python main.py discover --count 4 --firestore   # run again → "already seen" hard-rejects
```
Offline, the same behaviour is proven by the test
`tests/test_discovery_loop_cli.py::test_run_discover_is_idempotent_across_runs`.

## 4. Close the loop: discover → tailor (optional)
Feed the top match straight into the existing résumé Tailor (needs a completed grill
session id):
```bash
python main.py discover --count 4 --tailor-session <YOUR_GRILL_SESSION_ID> -o tailored.pdf
```

## Talking points to hit on screen (rubric-aligned)
- **Multi-agent (A2A):** two decoupled agents, typed `EvaluationDiff` contract, not prose.
- **MCP server:** real FastMCP server is the sandboxed data boundary; Scout is the client.
- **Security:** live source needs **no key**; `fetch_jd` is SSRF-guarded; nothing secret persisted.
- **Cost routing:** cheap deterministic hard-reject gate before the Pro-tier evaluation; bounded loop.
- **Idempotency / deployability:** stable `job_id` hash; re-runs never dupe; reuses the deployed Tailor.
