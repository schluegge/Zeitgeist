# Zeitgeist CI and Verify Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first fork-native CI workflow and one cross-platform `cargo xtask zeitgeist-verify` command that verifies the development-system surface without introducing any Zeitgeist runtime dependency.

**Architecture:** Add a focused xtask module that owns a deterministic list of Cargo-based checks and executes them fail-fast with contextual errors. Add a hand-maintained GitHub Actions workflow that invokes the same command on pinned Ubuntu 24.04 and Windows 2025 GitHub-hosted runners; keep it outside Zed's generated workflow set so upstream regeneration cannot delete it.

**Tech Stack:** Rust 1.97.1, Clap, anyhow, existing `xtask`, GitHub Actions, existing workflow validator.

## Global Constraints

- This system exists to develop Zeitgeist; it is not a Zeitgeist product feature or runtime dependency.
- Development infrastructure stays under `tooling/`, `script/`, `.github/`, docs, or development-only local state.
- Third-party GitHub actions are pinned to full immutable commit SHAs.
- CI uses GitHub-hosted runners and no Zed/Namespace secrets, owner guards, or custom runners.
- The canonical interface is `cargo xtask zeitgeist-verify`; CI uses `--profile ci`.
- Evidence persistence, source indexing, OpenTelemetry, product-wide impact analysis, and canonical README replacement are out of scope for this slice.

---## File map

- Create `tooling/xtask/src/tasks/zeitgeist_verify.rs`: profile selection, deterministic check plan, subprocess execution, unit tests.
- Modify `tooling/xtask/src/tasks.rs`: export the new verifier task.
- Modify `tooling/xtask/src/main.rs`: expose `ZeitgeistVerify` as a flat Clap subcommand.
- Create `.github/workflows/zeitgeist_ci.yml`: fork-native CI entry point using only GitHub-hosted runners.

### Task 1: Add the verifier command and test its check plan

**Files:**
- Create: `tooling/xtask/src/tasks/zeitgeist_verify.rs`
- Modify: `tooling/xtask/src/tasks.rs`
- Modify: `tooling/xtask/src/main.rs`

**Interfaces:**
- Consumes: Cargo from `CARGO` when set, otherwise `cargo` from `PATH`.
- Produces: `cargo xtask zeitgeist-verify [--profile fast|ci]` returning zero only when every required check succeeds.
- Produces internally: `VerificationProfile::{Fast,Ci}`, `Check { id, args }`, `checks(profile) -> Vec<Check>`, and `run(args) -> anyhow::Result<()>`.

- [ ] **Step 1: Add failing unit tests for profile selection**

Create the module with the types and tests first, leaving `checks` unimplemented so the test fails to compile:```rust
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, clap::ValueEnum)]
enum VerificationProfile {
    #[default]
    Fast,
    Ci,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Check {
    id: &'static str,
    args: &'static [&'static str],
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ids(profile: VerificationProfile) -> Vec<&'static str> {
        checks(profile).into_iter().map(|check| check.id).collect()
    }

    #[test]
    fn fast_profile_contains_deterministic_local_checks() {
        assert_eq!(ids(VerificationProfile::Fast), ["format", "xtask-tests", "workflow-validation"]);
    }
``````rust
    #[test]
    fn ci_profile_adds_xtask_clippy() {
        assert_eq!(
            ids(VerificationProfile::Ci),
            ["format", "xtask-clippy", "xtask-tests", "workflow-validation"]
        );
    }
}
```

- [ ] **Step 2: Wire the module and confirm the tests fail**

Add `pub mod zeitgeist_verify;` to `tooling/xtask/src/tasks.rs`, but do not implement `checks` yet.

Run: `cargo test -p xtask zeitgeist_verify`

Expected: FAIL at compile time because `checks` is not defined.

- [ ] **Step 3: Implement the deterministic check plan**

Add this function to `zeitgeist_verify.rs`:```rust
fn checks(profile: VerificationProfile) -> Vec<Check> {
    let mut checks = vec![Check {
        id: "format",
        args: &["fmt", "--all", "--", "--check"],
    }];

    if profile == VerificationProfile::Ci {
        checks.push(Check {
            id: "xtask-clippy",
            args: &["xtask", "clippy", "--package", "xtask"],
        });
    }

    checks.extend([
        Check {
            id: "xtask-tests",
            args: &["test", "-p", "xtask"],
        },
        Check {
            id: "workflow-validation",
            args: &["xtask", "check-workflows"],
        },
    ]);
    checks
}
```

Run: `cargo test -p xtask zeitgeist_verify`
Expected: PASS for both profile-selection tests.- [ ] **Step 4: Implement fail-fast execution and expose the CLI**

Add imports and the public argument/runner interface:

```rust
use std::{env, ffi::OsString, process::Command};
use anyhow::{Context as _, Result, bail};
use clap::{Parser, ValueEnum};

#[derive(Parser)]
pub struct ZeitgeistVerifyArgs {
    #[arg(long, value_enum, default_value = "fast")]
    profile: VerificationProfile,
}

pub fn run(args: ZeitgeistVerifyArgs) -> Result<()> {
    let cargo = env::var_os("CARGO").unwrap_or_else(|| OsString::from("cargo"));
    for check in checks(args.profile) {
        eprintln!("==> {}", check.id);
        let status = Command::new(&cargo)
            .args(check.args)
            .status()
            .with_context(|| format!("failed to start Zeitgeist verification check `{}`", check.id))?;
        if !status.success() {
            bail!("Zeitgeist verification check `{}` failed with {status}", check.id);
        }
    }
    Ok(())
}
```In `tooling/xtask/src/main.rs`, add the flat subcommand and dispatch arm:

```rust
    /// Runs Zeitgeist development-system verification checks.
    ZeitgeistVerify(tasks::zeitgeist_verify::ZeitgeistVerifyArgs),
```

```rust
        CliCommand::ZeitgeistVerify(args) => tasks::zeitgeist_verify::run(args),
```

- [ ] **Step 5: Run focused tests and both command profiles locally**

Run: `cargo test -p xtask zeitgeist_verify`
Expected: PASS.

Run: `cargo xtask zeitgeist-verify`
Expected: format, xtask tests, and workflow validation all PASS.

Run: `cargo xtask zeitgeist-verify --profile ci`
Expected: the fast checks plus xtask Clippy all PASS.

- [ ] **Step 6: Commit the verifier**

```powershell
git add tooling/xtask/src/main.rs tooling/xtask/src/tasks.rs tooling/xtask/src/tasks/zeitgeist_verify.rs
git commit -m "Add Zeitgeist verification command"
```

### Task 2: Add fork-native GitHub Actions CI**Files:**
- Create: `.github/workflows/zeitgeist_ci.yml`

**Interfaces:**
- Consumes: `cargo xtask zeitgeist-verify --profile ci` from Task 1.
- Produces: workflow `Zeitgeist CI`, triggered by pushes, pull requests, merge groups, and manual dispatch.
- Runs on: `ubuntu-24.04` and `windows-2025` GitHub-hosted x64 runners.

- [ ] **Step 1: Create the workflow with least-privilege permissions and immutable checkout**

```yaml
name: Zeitgeist CI

on:
  merge_group: {}
  pull_request:
    branches: ['**']
  push:
    branches: ['**']
  workflow_dispatch: {}

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
``````yaml
jobs:
  development_system:
    name: Development system (${{ matrix.os }})
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-24.04, windows-2025]
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30
    steps:
      - name: Checkout repository
        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd
        with:
          fetch-depth: 0
      - name: Verify development system
        run: cargo xtask zeitgeist-verify --profile ci
```

The workflow deliberately uses no repository secrets, no `pull_request_target`, no custom runner labels, and no mutable action tag.

- [ ] **Step 2: Validate the workflow with the repository validator**

Run: `cargo xtask check-workflows`
Expected: PASS with `.github/workflows/zeitgeist_ci.yml` included in validation.

- [ ] **Step 3: Verify Zed workflow generation preserves the manual workflow**Run:

```powershell
cargo xtask workflows
git diff --exit-code -- .github/workflows/run_tests.yml
git status --short -- .github/workflows/zeitgeist_ci.yml
```

Expected: generated Zed workflow output is unchanged; `zeitgeist_ci.yml` still exists and remains a normal tracked/manual workflow candidate.

- [ ] **Step 4: Run the CI profile once more with the workflow present**

Run: `cargo xtask zeitgeist-verify --profile ci`
Expected: PASS, including workflow validation of `zeitgeist_ci.yml`.

- [ ] **Step 5: Commit the fork-native workflow**

```powershell
git add .github/workflows/zeitgeist_ci.yml
git commit -m "Add Zeitgeist fork-native CI"
```

### Task 3: Verify the complete first slice

**Files:**
- No new files; verification only.

**Interfaces:**
- Consumes: Task 1 command and Task 2 workflow.
- Produces: local proof that the committed slice is internally consistent before push.- [ ] **Step 1: Run focused verifier tests**

Run: `cargo test -p xtask zeitgeist_verify`
Expected: PASS.

- [ ] **Step 2: Run the complete CI verification profile**

Run: `cargo xtask zeitgeist-verify --profile ci`
Expected: all four checks PASS and command exits 0.

- [ ] **Step 3: Verify repository cleanliness and commit sequence**

Run:

```powershell
git status --short
git log -4 --oneline
```

Expected: clean worktree. The recent history contains the design/spec commit, this implementation-plan commit, verifier commit, and fork-native CI commit.

- [ ] **Step 4: Push the isolated branch and inspect the actual GitHub Actions run**

Run: `git push -u origin agent/zed-first-sdlc-foundation/zg-20260813-1206`

Then query the repository Actions runs for workflow `Zeitgeist CI` and verify both `ubuntu-24.04` and `windows-2025` jobs execute rather than being skipped. Any remote failure is treated as a real CI defect and fixed on this branch before integration.

---

## Exit criteria

The slice is complete only when the local CI profile passes, the manual workflow survives `cargo xtask workflows`, the branch is clean, and GitHub reports a non-skipped `Zeitgeist CI` run. Product-runtime dependency graphs remain untouched.