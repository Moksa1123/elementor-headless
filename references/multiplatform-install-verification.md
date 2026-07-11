# Multi-Platform Install Conventions — Verified 2026-07-11

This skill supports installing into multiple AI coding assistants, following
the pattern pioneered by [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp).
**This table has an expiry date.** The table below was current as of the date
in the heading; this ecosystem moves fast enough that a 6-week-old assumption
had already gone stale in 3 of 8 platforms the last time this was checked (see
"Known drift" at the bottom). Re-verify before trusting, especially for any
platform not already marked `verified: true` in its
`assets/templates/platforms/*.json`.

| Platform | Install type | Path | Frontmatter | Notes |
|---|---|---|---|---|
| claude-code | full | `.claude/skills/<name>/SKILL.md` (project) or `~/.claude/skills/<name>/SKILL.md` (global) | `name` (must match folder name) + `description` (required) | Auto-loads at session start. Optional fields exist for extended trigger guidance, `argument-hint`, `fork` (isolated subagent), reasoning-effort control, explicit-invoke-only mode. |
| claude-ai | zip-upload | Settings → Skills → Upload | `name` + `description` | Zip must contain the skill folder itself at the root, not just SKILL.md at the top level. Private to the uploading account. |
| cursor | rule | `.cursor/rules/<name>.mdc` | `description`, `globs`, `alwaysApply` | Subdirectories are supported (`.cursor/rules/frontend/x.mdc`). Four activation modes: Always Apply, Auto Attached (globs), Agent Requested (description), Manual (`@rule-name`). The legacy single `.cursorrules` file still works but is not the recommended format. |
| codex-cli | full | `.codex/skills/<name>/SKILL.md` (project) or `~/.codex/skills/<name>/SKILL.md` (personal) | `name` + `description` | Natively supports the same SKILL.md spec as Claude Code. A parallel, broader cross-tool convention `.agents/skills/` (searched from cwd up to repo root, then `~/.agents/skills/`) also exists — check which your Codex CLI version prioritizes. |
| gemini-cli | full | `.gemini/skills/<name>/SKILL.md` (project) or `~/.gemini/skills/<name>/SKILL.md` (personal) | `name` + `description` | **Changed since this skill's sibling project was built**: Gemini CLI now natively supports the SKILL.md standard directly — the same directory-based skill that works in Claude Code and Codex CLI works here unmodified. The older `.gemini/extensions/<name>/GEMINI.md` extension-context approach still works for bundling skills inside a distributable extension, but is no longer the only (or simplest) path for a standalone skill. |
| windsurf | rule | `.devin/rules/<name>.md` (current) or `.windsurf/rules/<name>.md` (fallback) | none — plain markdown, no special frontmatter; group related content with XML-style tags | **Changed since this skill's sibling project was built**: Cognition rebranded Windsurf to "Devin Desktop" (2026-06-02); windsurf.com now redirects to devin.ai. New projects should target `.devin/rules/`; `.windsurf/rules/` is kept working as a fallback for existing setups. Character limits apply (~12,000 chars per rule file). |
| copilot | full **or** instructions-append | `.github/skills/<name>/SKILL.md` (new, preferred) **or** append a fenced section to `.github/copilot-instructions.md` (legacy, still works) | none for the instructions file; SKILL.md form likely follows the same spec as other platforms | **Changed since this skill's sibling project was built**: GitHub Copilot added a proper `.github/skills/` Agent Skills directory (December 2025) alongside the older single-file `copilot-instructions.md` convention. Prefer the skills-directory form for new installs; keep the append-mode installer as a fallback for older Copilot versions. |
| continue | rule | `.continue/rules/<name>.md` (project) or `~/.continue/rules/<name>.md` (global) | `name`, `globs` (optional), `regex` (optional), `description` (optional) | `alwaysApply: true` (or no frontmatter) applies to every interaction; `alwaysApply: false` with `globs` scopes to matching files. Rule files load in lexicographic order — number-prefix filenames to control ordering. |

## Known drift (why you must re-verify, not just trust this table)

The sibling project (`rankmath-seo-wp`) shipped its own version of this table
on 2026-05-25. Re-checked on 2026-07-11 — roughly six and a half weeks later —
three of eight platforms had already changed in ways that would silently
mis-install the skill if the old table were trusted:

1. **Gemini CLI** moved from an extension-wrapped `GEMINI.md` context file to
   native `SKILL.md` support at `.gemini/skills/`.
2. **Windsurf** was rebranded to Devin Desktop mid-cycle, with a new preferred
   rules path (`.devin/rules/`) and the old path demoted to a compatibility
   fallback.
3. **GitHub Copilot** gained a real Agent Skills directory
   (`.github/skills/`), making the old instructions-append approach a
   fallback rather than the only option.

Two platforms were flagged as unverified from the start (codex-cli,
gemini-cli) precisely because the ecosystem was known to be evolving quickly
— that caution turned out to be warranted for one of the two. The other six
platforms held steady over the same period.

**Practical implication**: before installing into any platform, spend one
search confirming today's convention rather than trusting a config file that
may already be a release cycle behind. Update this file's date and the
per-platform `verified`/`verificationNote` fields whenever you do.
