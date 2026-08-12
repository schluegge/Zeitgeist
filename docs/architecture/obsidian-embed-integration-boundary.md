# Obsidian embed integration boundary

Status: implementation-boundary audit
Date: 2026-08-12
Base: `origin/main` at `457d8dad4dad30111307835b4cdf4b32c00c4352`

## Verified Obsidian behavior

Current Obsidian Help defines an embed as an internal link prefixed with `!`.
The same syntax can embed notes and supported attachment formats, so `![[...]]` is not an image-only construct.

The documented capability set includes:

- notes: `![[Note]]`;
- note headings and blocks: `![[Note#Heading]]`, `![[Note#^block]]`;
- images, including width/height modifiers after `|`;
- audio;
- PDFs, including `#page=N` and `#height=N` fragments;
- Canvas files.

For non-Markdown files, Obsidian internal links require the file extension. Markdown note extensions may be omitted.

Sources inspected on 2026-08-12:

- `obsidianmd/obsidian-help`, `en/Linking notes and files/Internal links.md`;
- `obsidianmd/obsidian-help`, `en/Linking notes and files/Embed files.md`.

## Current Zeitgeist boundary

`crates/markdown/src/parser.rs` enables `pulldown-cmark` Wikilinks and maps them to the existing link model.
There is no Zeitgeist parser-level embed construct for Obsidian `![[...]]` syntax.

The existing image path is a different semantic layer: `pulldown_cmark::Tag::Image` maps to `MarkdownTag::Image`, and `crates/markdown/src/markdown.rs` has image-specific loading/rendering behavior.
Treating every Obsidian embed as `MarkdownTag::Image` would therefore be incorrect for notes, audio, PDFs, and Canvas.

## First implementation slice

The first implementation slice should preserve the syntactic distinction between a normal Wikilink and an Obsidian embed before resource-type rendering is attempted.

Required behavior for that slice:

1. recognize `![[target]]` as an embed rather than plain text plus a normal link;
2. preserve the target string without forcing a resource type in the parser;
3. keep the existing `[[target]]` behavior unchanged;
4. keep embed syntax inert inside inline code and fenced code blocks;
5. add parser tests for note, attachment, alias/modifier, and code-literal cases.

Resolution and rendering should remain separate follow-up concerns. A resolver can determine whether the target is a Markdown note, image, audio, PDF, Canvas, or another supported resource and hand it to the appropriate renderer.

## Acceptance boundary

This audit does **not** claim that Zeitgeist renders Obsidian embeds.
It establishes the parser/resolver boundary needed to implement the feature without collapsing heterogeneous resources into the existing image pipeline.

The next task can be accepted when parser tests prove the five behaviors above and the full `markdown` test suite remains green.
