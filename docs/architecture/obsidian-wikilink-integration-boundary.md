# Obsidian wikilink integration boundary

## Scope

This audit recovers the stale `obsidian-basic-wikilinks` workstream without assuming its previous state. It identifies the smallest verified implementation boundary for basic Obsidian wikilinks on current Zeitgeist `origin/main`.

## Verified current behavior

- `crates/markdown/src/parser.rs` delegates Markdown syntax recognition to `pulldown_cmark::Parser` and only creates `MarkdownTag::Link` directly from `pulldown_cmark::Tag::Link` or from URL autolinking via `linkify`.
- No `wikilink` implementation exists in the current source tree.
- `crates/markdown/src/markdown.rs` already renders every `MarkdownTag::Link` through the existing link builder and link callback.
- `crates/markdown_preview/src/markdown_preview_view.rs` already routes clicked non-web links through `resolve_preview_path` and `Workspace::open_abs_path` when they resolve to an existing local path.
- Existing preview tests cover ordinary relative and URL-encoded local Markdown paths.

## Obsidian semantics that matter for the first slice

Obsidian documents `[[Three laws of motion]]` and `[[Three laws of motion.md]]` as equivalent internal links. Folder-qualified wikilinks are vault-root relative, and `[[Example|Custom name]]` changes only displayed link text. Heading and block references add further semantics and should not be silently treated as completed by a basic-file-link implementation.

Source inspected: Obsidian Help, “Internal links”, 12 August 2026: https://obsidian.md/help/links

## Integration boundary

The first missing boundary is **syntax recognition plus target normalization**, not a new renderer or workspace-opening subsystem.

A minimal implementation should:

1. recognize basic `[[target]]` and `[[target|display text]]` outside code spans/blocks;
2. emit the existing `MarkdownTag::Link` / text / `MarkdownTagEnd::Link` event shape with source ranges preserved;
3. normalize extensionless note targets so an existing `target.md` can resolve;
4. preserve the original source text byte-for-byte unless the editor explicitly edits it;
5. add parser tests for plain targets, explicit `.md`, aliases, adjacent text, and code exclusion;
6. add preview-path tests for extensionless `.md` resolution before claiming clickable compatibility.

## Deliberately not included in the first slice

- heading references (`#Heading`);
- block references (`#^block`);
- embeds (`![[...]]`);
- fuzzy basename resolution across folders;
- unresolved-link note creation;
- rename-time link rewriting;
- alias-property lookup.

These require separate behavior contracts and fixtures.

## Recovery conclusion

The previous stale implementation claim had no source changes in its worktree and was several commits behind current `origin/main`. Reusing that worktree would provide no implementation value. The safe next implementation slice is parser recognition plus extensionless local-note resolution on a fresh branch based on current `origin/main`.
