# Zeitgeist Development System Design

**Date:** 2026-08-13
**Status:** Design approved; written specification pending review
**Scope:** Development infrastructure used to build Zeitgeist

## Purpose

Zeitgeist needs an AI-driven software-development system that makes required engineering checks automatic rather than dependent on a human or agent remembering them.

This system exists **to develop Zeitgeist**. It is not a Zeitgeist product feature and must not become a runtime dependency of the application.

The development system must make it difficult to declare work complete without machine-readable evidence for the checks that apply to that change.

## Architectural boundary

Product runtime and development infrastructure are separate dependency domains.

Zeitgeist product crates may use Zed/GPUI, product-facing AI capabilities, Obsidian compatibility code, and other application dependencies. They must not depend on LangGraph orchestration, development source indexes, SDLC OpenTelemetry instrumentation, CI evidence storage, or development-only verification machinery.

Development infrastructure lives primarily under `tooling/`, `script/`, `.github/`, and development-only local state. It may inspect and invoke product code and repository tools, but the dependency direction never reverses.

Development state that does not belong in Git should live under a dedicated development namespace such as `%LOCALAPPDATA%\Zeitgeist\dev\...`.

## Approaches considered

### 1. Separate development repository

A separate repository would isolate development tooling completely, but version skew between product code and gates would become an operational risk. Repository-local scripts and CI changes would also require cross-repository coordination.

### 2. Development capabilities inside Zeitgeist

Embedding indexing, orchestration, evidence, and observability in the application would make reuse easy but would contaminate the product architecture with build-system concerns and increase runtime dependencies. This approach is rejected.

### 3. Repository-local, runtime-isolated development system

This is the selected approach. Development machinery is versioned with the source tree but remains outside the product runtime dependency graph. Local and CI execution use the same canonical entry point and evidence model.

## P0 components

### Zeitgeist-native CI

The fork needs workflows that actually execute in `schluegge/Zeitgeist` and use available runners. They must not depend on Zed-owned repository-owner gates, Namespace runners, Zed secrets, or upstream-only infrastructure.

Third-party actions must be pinned to immutable commit SHAs. Initial CI should prefer GitHub-hosted runners and reuse existing Zed scripts or xtasks instead of duplicating their logic. The first workflow is a dedicated non-generated `.github/workflows/zeitgeist_ci.yml`; the repository already supports non-generated workflows alongside xtask-generated ones, so this minimizes conflict with upstream Zed workflow generation.

### Canonical verification command

One repository command is the stable interface for both agents and CI: `cargo xtask zeitgeist-verify`. This follows the existing flat `xtask` Clap subcommand structure.

The command orchestrates existing checks rather than reimplementing them. It should support a fast local mode and a CI/full mode while preserving one evidence contract.

Initial checks should cover formatting, linting, generated-file freshness where relevant, focused tests, repository-specific static checks, and a build/smoke boundary appropriate to the changed surface.

### Canonical project truth

Agents must encounter Zeitgeist identity and architecture before stale inherited Zed or Glass framing. The root README and a canonical architecture document must describe the current product direction accurately.

Repository metadata should be updated separately through GitHub when permissions allow. Documentation identity is a development-system input because agents use it during discovery and planning.

### Verification evidence

Every development run must emit structured evidence sufficient to answer what was checked, against which Git state, with which outcome.

A minimal record contains a schema version, run identifier, Git commit/base/branch, dirty-state marker, check identifier, command or executor, start/end timestamps or duration, outcome, and artifact references when produced.

Human-readable console output remains useful, but machine-readable evidence is the authoritative completion input for orchestration and CI.

## Later development-system components

### Hybrid source-code index

The source index is a coding-agent discovery tool, not a Zeitgeist feature. It should combine Tree-sitter structural chunks, lexical retrieval, LSP relations, Git provenance, and embeddings.

Embedding hits are discovery evidence, not source-of-truth evidence. Agents must verify retrieved claims against current source, Tree-sitter structure, or LSP results before acting on them.

The documentation vector index remains separate. Its current scope is Markdown documentation; source indexing should not silently broaden that contract.

### Development observability

OpenTelemetry may instrument agent runs, orchestration, local verification, and CI. It must not require product telemetry changes and must not introduce OpenTelemetry dependencies into Zeitgeist runtime crates merely for SDLC observability.

Useful spans include discovery, retrieval, planning, edits, formatting, linting, structural checks, tests, docs checks, build, review, and evidence publication.

### Documentation freshness

The system should eventually map changed behavior or public surfaces to required documentation updates, generated documentation, or an explicit machine-readable justification that no documentation change is needed.

The documentation index can report provenance and staleness, but semantic documentation freshness requires explicit verification rules.

## Development flow

The target closed loop is:

`DISCOVER -> PLAN -> EDIT -> FAST VERIFY -> IMPACT ANALYSIS -> TEST -> DOC VERIFY -> BUILD -> CI -> INDEPENDENT REVIEW -> EVIDENCE GATE -> COMPLETE`

Discovery may use canonical architecture docs, documentation retrieval, source retrieval, Tree-sitter, LSP, and exact repository search.

Fast verification should fail early on cheap deterministic checks before expensive tests. Impact analysis determines which focused tests, docs, generated artifacts, and broader checks are required.

The evidence gate accepts only completed required checks for the exact Git state being evaluated. Evidence from another commit or from a materially different dirty worktree must not satisfy the gate.

## Failure behavior

A failed required check fails verification. A missing required tool is an infrastructure failure, not a successful skip.

Checks may be explicitly not applicable only when the verifier has a deterministic rule for that decision and records it in evidence.

CI must upload or retain enough evidence to diagnose failures without access to a developer machine. Local runs should keep evidence in development-only state and avoid polluting the repository.

The system must not silently convert unsupported upstream infrastructure into no-op success.

## Testing strategy

Development-system code requires its own focused tests. Evidence serialization and gate logic should be unit-tested with success, failure, stale-Git-state, dirty-worktree, missing-tool, and not-applicable cases.

The canonical verifier should have smoke tests that exercise command selection without requiring the entire Zed workspace to rebuild for every test of orchestration logic.

CI workflow validity should be checked using the repository's existing workflow generation/linting conventions where compatible. Zeitgeist-owned workflows must remain independently executable in the fork.

End-to-end acceptance requires a representative change to pass locally and in Zeitgeist CI with matching evidence semantics.

## Delivery order

1. Add Zeitgeist-native CI using available runners and no upstream-only secrets or owner gates.
2. Add the canonical local/CI verification entry point by composing existing repository checks.
3. Establish canonical Zeitgeist identity and architecture documentation.
4. Add the machine-readable evidence schema and bind both local verification and CI to it.
5. Add the hybrid source-code index as development-only agent infrastructure.
6. Add development-only OpenTelemetry tracing around orchestration and verification.
7. Add documentation freshness, coverage, flake history, security advisory checks, upstream-drift automation, and release verification incrementally.

## Non-goals

This design does not turn Zeitgeist into an SDLC product, developer-observability product, source-index server, or LangGraph application.

It does not require replacing Zed's existing tests, scripts, Tree-sitter integration, LSP implementation, or product telemetry. Existing mechanisms should be composed and extended only where Zeitgeist needs a missing development guarantee.

It does not require every future development check to land in the first implementation slice. P0 establishes the executable control plane into which later checks plug.

## Success criteria

The design is successful when an agent can work on Zeitgeist without separately remembering the required formatter, linter, tests, documentation checks, CI details, or evidence conventions for the supported change class.

The same verification contract must be usable locally and in Zeitgeist CI, failures must be explicit, and completion must be tied to evidence for the exact repository state.

No product-runtime crate should gain a dependency solely because the development system needs orchestration, indexing, verification evidence, or observability.
