# Zeitgeist Product Architecture

**Status:** Canonical product direction

This document defines the product boundary for Zeitgeist. It distinguishes architectural intent from features that are already verified in the repository.

## Product statement

Zeitgeist is a local workspace for knowledge, code, and AI-assisted work. It is built on Zed rather than beside it, and it is intended to use existing Obsidian vaults directly instead of importing them into a proprietary data model.

The canonical summary is:

> Zed is the technical core. Obsidian provides the file-based knowledge model and an important compatibility standard. Zeitgeist combines them into one local workspace for knowledge, software, and AI agents.

The user should not have to decide whether a local artifact is "a note", "documentation", "project context", "code", or "agent context" before it can participate in the workspace. The file remains the source of truth; Zeitgeist supplies the relevant editing, navigation, relationship, and agent surfaces around it.

## Foundations

### Zed

Zed is the technical foundation and active upstream. Zeitgeist should reuse Zed's GPUI, editor, project/worktree model, Git integration, terminal, language-server infrastructure, collaboration systems, and product-facing agent infrastructure wherever those capabilities already solve the problem.

Replacing mature Zed subsystems with parallel Zeitgeist-specific implementations requires concrete evidence that the upstream subsystem cannot satisfy the product requirement.

### Obsidian

Obsidian is a compatibility target, not Zeitgeist's technical foundation. Compatibility means preserving useful behavior around the existing file-based vault model: Markdown, YAML frontmatter, Obsidian link and embed syntax, attachments, `.obsidian/` configuration, and JSON Canvas are relevant compatibility surfaces.

These formats remain files on disk. Zeitgeist should not require a proprietary database migration before they can be used.

### Glass

Glass is a selective donor and reference. The repository's GitHub ancestry currently passes through Glass, but the product architecture is not "Glass plus newer Zed".

A Glass implementation should be transplanted only when it provides a capability or interaction that is still useful and is not already better supplied by current Zed.

### AI and agents

AI and agent capabilities are product features when they help operate on the user's local workspace. They should share the same project and knowledge context rather than requiring a detached knowledge silo.

Development orchestration for coding Zeitgeist is a different system. LangGraph workflows, coding-agent source indexes, CI evidence, and SDLC observability do not become product features merely because agents exist in the application.

## Compatibility model

Zeitgeist's Obsidian compatibility direction follows four rules:

1. Open existing vaults in place rather than requiring migration.
2. Keep ordinary files as the authoritative state.
3. Preserve unsupported content rather than silently transforming it into a proprietary representation.
4. Land compatibility in evidence-backed slices instead of claiming broad compatibility before tests exist.

The target compatibility surface includes Markdown and YAML semantics, wikilinks, embeds, attachments, vault configuration that is safe to ignore or preserve, and JSON Canvas. Each surface needs its own tests before it can be described as supported.

Compatibility does not require reproducing every Obsidian plugin API or every application behavior. The priority is direct use of durable user-owned files and the relationships needed for the Zeitgeist workspace model.

## Current evidence-backed baseline

The current Zed-first integration line contains `test_obsidian_vault_readonly_smoke` in `crates/project/tests/integration/project_tests.rs`, introduced by commit `f95847c123`.

That test creates a vault fixture containing:

- `.obsidian/app.json`;
- a Markdown note with YAML frontmatter;
- `[[Target]]` wikilink syntax;
- `![[attachment.txt]]` embed syntax;
- a referenced Markdown file;
- a plain attachment;
- a JSON Canvas file.

The test opens the vault through the project model, opens the Markdown buffer, verifies its text is unchanged, verifies the Canvas and hidden `.obsidian` file remain visible, and verifies every fixture path remains byte-identical after opening.

This is evidence for read-only in-place opening and preservation only. It is not evidence that wikilinks resolve, embeds render, Canvas renders, Obsidian plugins run, or the full Obsidian application model is compatible.

## Product boundary

Zeitgeist product runtime may contain or depend on capabilities required by the application itself: Zed/GPUI editor infrastructure, project and worktree state, local file relationships, product-facing AI and agent features, Obsidian compatibility behavior, Git, terminals, language servers, collaboration, and UI needed to expose those capabilities.

A capability belongs in the product only when the application needs it at runtime or as part of the user's direct workflow. Development convenience alone is not sufficient.

## Development-system boundary

The development system exists to build Zeitgeist. Its normal home is `tooling/`, `script/`, `.github/`, development documentation, and local development state outside the product data model.

Examples include:

- CI and runners;
- formatter, lint, tests, coverage, and benchmarks;
- Tree-sitter and language-server analysis used by coding agents;
- development documentation and source indexes;
- LangGraph development orchestration;
- verification evidence and completion gates;
- development-only OpenTelemetry tracing;
- upstream drift, dependency, security, and release checks.

Product runtime crates must not depend on these systems solely because development automation needs them. The development system may inspect and invoke product code; the dependency direction does not reverse.

Canonical project documentation is part of the development-system input surface because coding agents use repository context during discovery and planning. That is why stale root identity is treated as a verification defect rather than cosmetic documentation debt.

## Non-goals

Zeitgeist is not an Obsidian clone, a Glass rebrand, an editor rewritten from scratch, a LangGraph application, or a proprietary migration layer around Markdown.

It does not treat every Obsidian feature as mandatory, every Glass feature as inherited product scope, or every development-agent capability as an application feature.

## Decision test

For a proposed architectural change, answer these questions in order:

1. Does current Zed already provide the technical capability? If yes, prefer reuse or extension over a parallel subsystem.
2. Does the change preserve the local file as authoritative state where the artifact is file-based?
3. If the change is described as Obsidian compatibility, what exact behavior is covered by a test or other reproducible evidence?
4. If the implementation comes from Glass, what capability is missing from current Zed and why is the Glass version still the better donor?
5. Does the capability need to exist in the user's running application, or only in the system used to develop Zeitgeist?
6. Does the documentation describe current evidence separately from future target behavior?

If a proposal fails the runtime-versus-development question, it belongs in the development system rather than a product crate. If it cannot state evidence for a compatibility claim, the claim remains a target rather than an implemented feature.
