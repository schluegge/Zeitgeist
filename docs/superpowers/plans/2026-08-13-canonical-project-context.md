# Canonical Zeitgeist Project Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Zeitgeist identity and product architecture the first reliable context seen by humans and coding agents, and fail verification if inherited Zed/Glass framing becomes canonical again.

**Architecture:** Keep product truth in two human-readable files: the root `README.md` for orientation and `docs/architecture/zeitgeist-product-architecture.md` for the canonical product boundary. Add a small development-only `xtask` validator and invoke it from `cargo xtask zeitgeist-verify`; do not add product-runtime dependencies.

**Tech Stack:** Markdown, Rust `xtask`, Clap, existing Zeitgeist verification gate, GitHub repository metadata.

## Global Constraints

- Zeitgeist product runtime must remain independent of SDLC infrastructure.
- Zed is the technical foundation; Obsidian is a compatibility target; Glass is only a selective donor/reference.
- Existing vault files remain the intended source of truth; do not claim full Obsidian compatibility.
- The only currently verified Obsidian behavior in this branch is the read-only vault-opening smoke test from `f95847c123`.
- Repository metadata is updated separately from versioned documentation and only when permissions/tooling allow a verified write.
- No product crate or product manifest changes belong in this slice.

---
### Task 1: Establish canonical human-readable project truth

**Files:**
- Modify: `README.md`
- Create: `docs/architecture/zeitgeist-product-architecture.md`

**Interfaces:**
- Produces: a stable README link to `./docs/architecture/zeitgeist-product-architecture.md`.
- Produces: canonical architecture headings consumed by the identity validator in Task 2.

- [ ] **Step 1: Rewrite the root README around Zeitgeist**

The README must begin with `# Zeitgeist` and state that Zeitgeist is a local workspace for knowledge, code, and AI-assisted work built on Zed/GPUI. It must distinguish current evidence from future compatibility goals and retain accurate licensing/build guidance.

- [ ] **Step 2: Add the canonical architecture document**

Create `docs/architecture/zeitgeist-product-architecture.md` with these stable section headings:

```markdown
# Zeitgeist Product Architecture
## Product statement
## Foundations
## Compatibility model
## Current evidence-backed baseline
## Product boundary
## Development-system boundary
## Non-goals
## Decision test
```
- [ ] **Step 3: Verify the documentation is internally consistent**

Check `README.md` and the canonical architecture document for inherited top-level Zed or Glass branding. Expected: no canonical-title or Glass-slogan matches remain.

Check the same files for `Zed`, `Obsidian`, `Glass`, `development system`, and `read-only`. Expected: each term appears only in its explicitly bounded role.

- [ ] **Step 4: Commit the documentation truth**

Stage only `README.md` and `docs/architecture/zeitgeist-product-architecture.md`, then commit with message `Establish canonical Zeitgeist project context`.

### Task 2: Add a machine-enforced project identity validator

**Files:**
- Create: `tooling/xtask/src/tasks/zeitgeist_identity.rs`
- Modify: `tooling/xtask/src/tasks.rs`
- Modify: `tooling/xtask/src/main.rs`
**Interfaces:**
- Produces: `pub struct ZeitgeistIdentityArgs`.
- Produces: `pub fn run(args: ZeitgeistIdentityArgs) -> anyhow::Result<()>`.
- Produces: pure validation helpers that accept README and architecture text for focused unit tests.

- [ ] **Step 1: Write failing validator tests**

Add tests proving rejection of:
- a README whose first heading is `# Zed`;
- a README that does not link the canonical architecture file;
- an architecture document missing the `## Development-system boundary` section.

Also add one success fixture containing all required markers.

- [ ] **Step 2: Run the focused test and verify RED**

Run `cargo test -p xtask zeitgeist_identity`.

Expected: compilation/test failure because the validator implementation does not yet exist.

- [ ] **Step 3: Implement the minimal validator**

Read `README.md` and `docs/architecture/zeitgeist-product-architecture.md` from the repository root. Validate stable headings/link markers only; do not attempt semantic NLP validation.
The required contract is:
- first non-empty README line is `# Zeitgeist`;
- README contains `./docs/architecture/zeitgeist-product-architecture.md`;
- architecture first non-empty line is `# Zeitgeist Product Architecture`;
- architecture contains every stable Task 1 section heading.

- [ ] **Step 4: Register the `zeitgeist-identity` xtask subcommand**

Wire `ZeitgeistIdentity(tasks::zeitgeist_identity::ZeitgeistIdentityArgs)` into the existing Clap command enum and dispatch it to `tasks::zeitgeist_identity::run`.

- [ ] **Step 5: Run focused tests and command**

Run `cargo test -p xtask zeitgeist_identity` and `cargo xtask zeitgeist-identity`.

Expected: all focused tests pass and the command exits 0 against the real repository documents.

- [ ] **Step 6: Commit the validator**

Stage only the identity task and its `xtask` registration files. Commit with message `Enforce canonical Zeitgeist project identity`.

### Task 3: Bind identity validation into the canonical verification gate

**Files:**
- Modify: `tooling/xtask/src/tasks/zeitgeist_verify.rs`

**Interfaces:**
- Consumes: `cargo xtask zeitgeist-identity` from Task 2.
- Produces: a required `project-identity` check in both fast and CI profiles.
- [ ] **Step 1: Update the existing check-order tests first**

Change the expected fast profile order to:
`format`, `project-identity`, `xtask-tests`, `workflow-validation`.

Change the expected CI profile order to:
`format`, `project-identity`, `xtask-clippy`, `xtask-tests`, `workflow-validation`.

- [ ] **Step 2: Run the tests and verify RED**

Run `cargo test -p xtask zeitgeist_verify`.

Expected: the profile-order tests fail because `project-identity` is not yet selected.

- [ ] **Step 3: Add the identity command to both profiles**

Add a `Check` with id `project-identity` and args `xtask zeitgeist-identity` immediately after formatting.

- [ ] **Step 4: Verify GREEN and the real fast gate**

Run `cargo test -p xtask zeitgeist_verify`, then `cargo xtask zeitgeist-verify`.

Expected: tests pass and the real gate exits 0.

- [ ] **Step 5: Commit the gate integration**

Stage only `tooling/xtask/src/tasks/zeitgeist_verify.rs`. Commit with message `Gate verification on Zeitgeist project identity`.

### Task 4: Verify the slice and correct remote repository metadata

**Files:**
- No additional product files.
- Remote metadata: `schluegge/Zeitgeist` description/homepage only if a verified GitHub API write is available.
- [ ] **Step 1: Run full development-system verification**

Run `cargo xtask zeitgeist-verify --profile ci` and confirm format, project identity, xtask Clippy, xtask tests, and workflow validation all exit 0.

- [ ] **Step 2: Verify scope isolation**

Compare against base `3a33be32cf`. Expected changed paths are limited to `README.md`, `docs/architecture/`, `docs/superpowers/plans/`, and `tooling/xtask/`.

Explicitly verify no product `Cargo.toml` or `crates/` path changed.

- [ ] **Step 3: Check current GitHub repository metadata using the authenticated API**

Record the current description and homepage immediately before any write. Do not infer them from the inherited fork.

- [ ] **Step 4: If supported, replace stale Glass metadata**

Set the description to: `Local workspace for knowledge, code, and AI-assisted work, built on Zed and designed for in-place Obsidian vault compatibility.`

Clear the stale Glass homepage unless there is a verified Zeitgeist project homepage. Do not invent a project website.

- [ ] **Step 5: Re-read GitHub metadata after the write**

Expected: description matches exactly and homepage no longer points to `glassapp.dev`.

- [ ] **Step 6: Push the feature branch and verify Zeitgeist CI**

Push the branch, then verify the `Zeitgeist CI` workflow executes rather than skips and succeeds for the exact pushed SHA on Ubuntu and Windows.

## Completion criteria

The slice is complete only when the root context is Zeitgeist-first, the canonical architecture file exists, the identity validator is mandatory in the local/CI gate, no product runtime files changed, and any remote metadata write is re-read and verified.
