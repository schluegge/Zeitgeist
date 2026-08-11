# LangGraph Orchestration Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and calibrate an isolated, provider-neutral LangGraph orchestration substrate for Zeitgeist development work without coupling Zeitgeist product state to LangGraph.

**Architecture:** A standalone uv-managed Python package under `tooling/agent-orchestration` owns workflow state, deterministic routing, side-effect guards, evidence gates, and local evaluation fixtures. LangGraph supplies execution semantics; LangSmith supplies optional tracing/evaluation, disabled by default and never required for correctness.

**Tech Stack:** Python 3.13, uv, LangChain, LangGraph, LangSmith, `langgraph-cli[inmem]`, pytest.

## Global Constraints

- Work only on branch `infra/langgraph-orchestration` in `C:\ZEITGEIST.worktrees\langgraph-orchestration`.
- Base commit is `fbc6b9aeafab846aedeef1c7ed35e78162cbe6a7`.
- Never push to remotes `glass` or `zed`.
- Keep provider-specific LangChain packages absent.
- Keep `LANGSMITH_TRACING=false` by default and commit no credentials.
- Workflow state is explicit structured data, never conversational memory.
- Every side effect validates preconditions, records change evidence, and is verified.
- `DONE` is unreachable without mandatory evidence.
- Deterministic safety gates: wrong-upstream push rate = 0, false-success rate = 0, missing mandatory evidence = 0.

---

### Task 1: Create isolated Python package and lock dependencies

**Files:**
- Create: `tooling/agent-orchestration/pyproject.toml`
- Create: `tooling/agent-orchestration/uv.lock`
- Create: `tooling/agent-orchestration/.env.example`
- Create: `tooling/agent-orchestration/langgraph.json`

**Interfaces:**
- Produces importable package `zeitgeist_orchestration` and local CLI/test environment.

- [ ] **Step 1:** Run `uv init --package --python 3.13 --vcs none --no-readme tooling/agent-orchestration` and inspect the generated metadata before retaining it.
- [ ] **Step 2:** Add current compatible `langchain`, `langgraph`, `langsmith`, `langgraph-cli[inmem]`, and dev dependency `pytest` with uv; let uv resolve versions and create `uv.lock`.
- [ ] **Step 3:** Verify `uv run python -c "import langchain, langgraph, langsmith"` and `uv run langgraph --help` both exit 0.
- [ ] **Step 4:** Configure `.env.example` with `LANGSMITH_TRACING=false`, `LANGSMITH_PROJECT=zeitgeist-orchestration-dev`, and an empty `LANGSMITH_API_KEY` placeholder only.
- [ ] **Step 5:** Configure `langgraph.json` to load the local package/graph without real credentials.

### Task 2: Explicit state and evidence-gated graph

**Files:**
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/state.py`
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/graph.py`
- Create: `tooling/agent-orchestration/tests/test_graph.py`

**Interfaces:**
- Produces `WorkflowState`, `WorkflowStatus`, `WorkflowPhase`, and compiled `graph`.

- [ ] **Step 1: Write failing graph-state tests**

```python
def test_done_requires_mandatory_evidence():
    result = graph.invoke(make_state(objective="audit", evidence=[]))
    assert result["status"] != "DONE"
```

- [ ] **Step 2:** Run the focused test and verify RED because graph/state implementation is absent.
- [ ] **Step 3:** Implement the minimal typed state and graph nodes `DISCOVER → AUDIT → PLAN → EXECUTE → VERIFY → REVIEW → COMMIT → DONE` with explicit alternate statuses.
- [ ] **Step 4:** Implement an evidence gate that requires verification artifacts before `DONE`.
- [ ] **Step 5:** Run focused tests and verify GREEN, then run the complete package test suite.

### Task 3: Deterministic tool routing and Git safety

**Files:**
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/routing.py`
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/git_safety.py`
- Create: `tooling/agent-orchestration/tests/test_routing.py`
- Create: `tooling/agent-orchestration/tests/test_git_safety.py`

**Interfaces:**
- Produces `route_tool(question) -> str` and `validate_git_effect(remote, expected_head, actual_head) -> GuardResult`.

- [ ] **Step 1: Write failing routing and safety tests**

```python
def test_gpui_docs_route_to_grounded_docs():
    assert route_tool("What does the current GPUI documentation say about X?") == "grounded_docs"

def test_glass_push_is_blocked():
    assert not validate_git_effect("glass", "abc", "abc").allowed
```

- [ ] **Step 2:** Run focused tests and verify RED because routing/guard implementations are absent.
- [ ] **Step 3:** Implement deterministic routing for Grounded Docs, Code Review Graph, rust-analyzer/LSP, and Code-Graph-RAG fixture questions.
- [ ] **Step 4:** Implement fail-closed Git guard blocking `glass`/`zed` and stale-HEAD effects before any command execution.
- [ ] **Step 5:** Run focused tests and complete package tests; verify GREEN.

### Task 4: Recovery, idempotence, and local evidence

**Files:**
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/evidence.py`
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/recovery.py`
- Create: `tooling/agent-orchestration/tests/test_recovery.py`
- Create: `tooling/agent-orchestration/tests/test_idempotence.py`

**Interfaces:**
- Produces immutable evidence records and idempotency decisions consumed by graph verification.

- [ ] **Step 1:** Write failing tests for command failure, stale HEAD, test failure, missing documentation, timeout, retry exhaustion, and second-run idempotence.
- [ ] **Step 2:** Run focused tests and verify each failure is RED for the intended missing behavior.
- [ ] **Step 3:** Implement minimal recovery classification and idempotency ledger using only per-run structured state/local artifacts.
- [ ] **Step 4:** Verify failed operations cannot claim success and repeated completed operations do not duplicate side effects.
- [ ] **Step 5:** Run the complete package tests and verify GREEN.

### Task 5: Permanent calibration corpus and baseline

**Files:**
- Create: `tooling/agent-orchestration/evals/cases.json`
- Create: `tooling/agent-orchestration/src/zeitgeist_orchestration/evals.py`
- Create: `tooling/agent-orchestration/tests/test_evals.py`
- Generate: `tooling/agent-orchestration/evals/baseline.json`

**Interfaces:**
- Produces deterministic evaluation metrics and machine-readable baseline artifact.

- [ ] **Step 1:** Write a failing test asserting exactly 24 unique high-signal cases and the three zero-tolerance safety gates.
- [ ] **Step 2:** Run focused test and verify RED while corpus/baseline implementation is absent.
- [ ] **Step 3:** Add 24 cases covering repository audit (4), routing (6), Git safety (3), recovery (6), evidence completeness (3), idempotence (2).
- [ ] **Step 4:** Implement local evaluator measuring routing correctness, task success, evidence completeness, unsupported-claim rate, unsafe-side-effect rate, recovery correctness, tool-call count, latency, and token usage when measurable.
- [ ] **Step 5:** Use LangSmith evaluation APIs only in offline mode (`upload_results=False`) when invoked; correctness must not depend on LangSmith network access.
- [ ] **Step 6:** Run calibration, write `evals/baseline.json`, and verify wrong-upstream push rate, false-success rate, and missing mandatory evidence are all exactly zero.

### Task 6: Final verification and repository integrity

**Files:**
- Inspect all files above; modify only to fix verified defects.

- [ ] **Step 1:** Run `uv sync --locked` from a clean local environment and verify dependency reproducibility.
- [ ] **Step 2:** Run `uv run pytest -q` and record test count/failures.
- [ ] **Step 3:** Run import smoke test and `uv run langgraph --help`.
- [ ] **Step 4:** Run the minimal compiled graph once through success and once through injected failure; inspect returned evidence/status.
- [ ] **Step 5:** Verify `LANGSMITH_TRACING=false` execution succeeds with no API key and offline evaluation performs no upload.
- [ ] **Step 6:** Inspect `git status`, `git diff --check`, branch HEAD/base, worktree list, `main`, and `sync/zed-2026-08-12` to prove isolation.
- [ ] **Step 7:** Scan tracked/untracked orchestration files for secret-shaped values before any commit.
- [ ] **Step 8:** Commit only verified orchestration artifacts to `infra/langgraph-orchestration`; do not push or merge.

## Self-review result

- The plan covers the handoff completion gate through calibration and repository-integrity verification.
- Provider integrations remain absent.
- Product architecture is untouched.
- All behavior-bearing implementation tasks use explicit RED/GREEN verification.
- No test writes to canonical Zeitgeist history or upstream remotes.
