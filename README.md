# Zeitgeist

Zeitgeist is a local workspace for knowledge, code, and AI-assisted work. It uses Zed and GPUI as its technical foundation and is being built to open existing Obsidian vaults in place, without migrating them into proprietary storage.

Zeitgeist is under active development. Obsidian compatibility is a target, not a claim of complete compatibility today.

## Product direction

- **Zed is the technical core.** Zeitgeist reuses the editor, GPUI, project model, Git, terminal, language-server, collaboration, and agent foundations instead of rebuilding an editor platform.
- **Obsidian is a compatibility target.** Existing Markdown, YAML, links, embeds, attachments, configuration folders, and Canvas files should remain ordinary files and stay the source of truth.
- **Knowledge and software belong in one local workspace.** Notes, documentation, project context, and code should not require separate storage models.
- **AI belongs in the workspace.** Agent capabilities should operate against the same local project context rather than a detached proprietary knowledge store.
- **Glass is a selective donor, not the foundation.** Glass code or UX is reused only when it adds something that is still missing from the Zed-first architecture.

The canonical product boundary is documented in [Zeitgeist Product Architecture](./docs/architecture/zeitgeist-product-architecture.md).

## Current evidence-backed baseline

The current Zed-first branch includes a read-only Obsidian-vault smoke test. It opens a fixture containing `.obsidian/app.json`, Markdown with YAML and Obsidian link/embed syntax, an attachment, and a JSON Canvas file.

The test verifies that the Markdown buffer is read unchanged, the hidden Obsidian configuration file and Canvas file remain visible to the project model, and every fixture file remains byte-identical after opening. It does **not** prove wikilink resolution, embed rendering, Canvas rendering, plugin compatibility, or complete Obsidian behavior.

## Development

The canonical development-system entry point is:

```sh
cargo xtask zeitgeist-verify
```

For the CI profile:

```sh
cargo xtask zeitgeist-verify --profile ci
```

Platform build instructions remain inherited from the Zed codebase while Zeitgeist-specific build documentation is established:

- [macOS](./docs/src/development/macos.md)
- [Linux](./docs/src/development/linux.md)
- [Windows](./docs/src/development/windows.md)

Development orchestration, source indexing, verification evidence, CI observability, and related SDLC machinery are tooling **for building Zeitgeist**. They are not Zeitgeist product features and must not become application runtime dependencies.

## Upstream relationship

Zeitgeist is Zed-first. Zed is the active technical upstream and architectural base. The GitHub fork ancestry currently passes through Glass, but that ancestry does not define the product architecture.

Glass remains useful as a reference or donor for capabilities that are genuinely absent from Zed. New work should not treat Glass as the base to which Zed is retrofitted.

## Contributing and upstream-derived documentation

Much of the repository is still upstream Zed code and documentation. [CONTRIBUTING.md](./CONTRIBUTING.md) and the platform development guides therefore contain Zed-specific conventions that remain relevant to the inherited codebase.

Zeitgeist-specific architectural decisions take precedence where inherited documentation conflicts with [the canonical Zeitgeist architecture](./docs/architecture/zeitgeist-product-architecture.md).

## Licensing

This repository retains the upstream license structure. Source code is primarily licensed under GPL-3.0-or-later, with Apache-2.0 components where marked. See [LICENSE-GPL](./LICENSE-GPL) and [LICENSE-APACHE](./LICENSE-APACHE).

Third-party dependency license information must remain complete for repository compliance checks.
