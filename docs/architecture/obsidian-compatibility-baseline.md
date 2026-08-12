# Obsidian Vault Compatibility Baseline

Date: 2026-08-12
Base: `main` at `fbc6b9aeafab846aedeef1c7ed35e78162cbe6a7`

## Scope

This audit establishes the smallest evidence-backed compatibility boundary for opening an existing Obsidian vault without migration. It does not claim full Obsidian compatibility.

## External format evidence

- Obsidian vault content is addressable as files under a vault root; Obsidian URI accepts vault-relative file paths and absolute filesystem paths. Source: https://help.obsidian.md/Extending+Obsidian/Obsidian+URI
- JSON Canvas is an open storage/interchange format using the `.canvas` extension. Version 1.0 defines top-level `nodes` and `edges`, with text, file, link, and group node types. Source: https://jsoncanvas.org/spec/1.0/
- JSON Canvas explicitly permits implementation as an import, export, or storage format in other applications. Source: https://jsoncanvas.org/

## Current Zeitgeist baseline

| Capability | Evidence in current tree | Baseline status |
| --- | --- | --- |
| Open a filesystem-backed project/folder | Inherited Zed `project` / `workspace` implementation is present. | Existing substrate; needs a real-vault smoke test. |
| Edit `.md` as source text | Markdown language/preview crates are present (`crates/markdown`, `crates/markdown_preview`). | Existing substrate; Obsidian semantics are not established. |
| Obsidian wikilinks | Repository search found no `wikilink`, `wiki_link`, or dedicated `[[...]]` handling in Markdown/language crates. | Gap / unverified. |
| JSON Canvas `.canvas` | Repository search found no JSON Canvas or `.canvas` implementation; unrelated Rust `Canvas` test fixtures were the only matches. | Gap. |
| Properties/frontmatter semantics | No compatibility implementation was identified by this audit. | Gap / unverified. |
| `.obsidian` preservation | No migration is required to open a folder, but preservation has not yet been tested with a real fixture. | Needs round-trip fixture. |

## Search evidence

Commands executed against the isolated worktree:

```powershell
rg -n "frontmatter|wikilink|wiki link|\.canvas|markdown|Markdown" crates -g '*.rs'
rg -n "wikilink|wiki_link|\[\[" crates/markdown* crates/language* -g '*.rs'
rg -n "\.canvas|json.?canvas|Canvas" crates -g '*.rs'
```

The negative searches are evidence only for the searched tree and terminology; they are not proof that no adjacent generic parser can be reused.

## Dependency order

The next implementation slice should be a **read-only real-fixture vault smoke test**, not a new parser. The fixture should contain at minimum:

1. plain Markdown;
2. YAML properties;
3. a wikilink and embed;
4. an attachment;
5. `.obsidian/` metadata;
6. one JSON Canvas 1.0 file containing text, file, link, and group nodes.

Acceptance criterion: Zeitgeist opens the vault directory without rewriting any fixture bytes, all files remain discoverable, Markdown opens as text, and unsupported `.canvas` behavior is reported as unsupported rather than silently transformed. Hash the fixture before and after the smoke test.

Only after that baseline is captured should implementation split into semantic slices: properties, links/embeds, attachments/backlinks, then JSON Canvas parsing/rendering.
