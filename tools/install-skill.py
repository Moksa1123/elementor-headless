#!/usr/bin/env python3
"""Install the elementor-headless skill into any of 8 supported AI platforms.

Reads platform configs from assets/templates/platforms/*.json and writes the
skill content to the right path with the right filename and frontmatter.

Usage:
    python tools/install-skill.py --list
    python tools/install-skill.py --info claude-code
    python tools/install-skill.py claude-code              # project scope
    python tools/install-skill.py claude-code --global     # global scope
    python tools/install-skill.py cursor --to /path/to/proj
    python tools/install-skill.py claude-ai --to ./build   # builds zip
    python tools/install-skill.py --dry-run claude-code    # show plan only
    python tools/install-skill.py                          # interactive

Install types:
    full                — copies SKILL.md + references/ + tools/ + data/ + examples/
    rule                — writes a single .md/.mdc rule file with embedded refs
    instructions-append — appends a fenced section to copilot-instructions.md
    zip-upload          — bundles the skill as a zip for manual upload (Claude.ai)

Every platform config was verified against that platform's own current
documentation as of the date in its "verifiedAsOf" field — see
references/multiplatform-install-verification.md before trusting an old copy
of this tool against a newer platform version.

Exit codes: 0 = installed, 1 = failed, 2 = invocation error
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = REPO_ROOT / "assets" / "templates" / "platforms"


def list_platforms() -> list[Path]:
    return sorted(PLATFORMS_DIR.glob("*.json"))


def load_platform(name: str) -> dict:
    p = PLATFORMS_DIR / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"Unknown platform: {name}\nRun --list to see options.")
    return json.loads(p.read_text(encoding="utf-8"))


def expand_path(s: str | None) -> Path | None:
    if s is None:
        return None
    return Path(os.path.expanduser(s))


def build_frontmatter(fm: dict | None) -> str:
    """Render a YAML frontmatter block from a dict (no PyYAML dep)."""
    if not fm:
        return ""
    lines = ["---"]
    for k, v in fm.items():
        if v is None:
            continue
        if isinstance(v, list):
            joined = ", ".join(json.dumps(x, ensure_ascii=False) for x in v)
            lines.append(f"{k}: [{joined}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, str) and ("\n" in v or len(v) > 100):
            lines.append(f"{k}: |")
            for sub in v.splitlines():
                lines.append(f"  {sub}")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def read_skill_body() -> str:
    """Strip the existing frontmatter from SKILL.md so we can re-wrap it."""
    raw = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            return raw[end + 4:].lstrip("\n")
    return raw


def embed_references(names: list[str]) -> str:
    """
    Concatenate selected reference files for platforms that can only take one flat
    document.

    A missing file is a hard error, not a skip. Silently shipping a rule file that
    is quietly missing a reference the platform config asked for is exactly the
    class of failure this whole skill exists to stamp out: it installs fine, it
    looks fine, and the agent is short one document it was supposed to have.
    """
    parts: list[str] = []
    for n in names:
        p = REPO_ROOT / "references" / n
        if not p.exists():
            available = ", ".join(sorted(q.name for q in (REPO_ROOT / "references").glob("*.md")))
            raise SystemExit(
                f"Platform config asks to embed references/{n}, which does not exist.\n"
                f"Available: {available}\n"
                f"Fix the platform config in assets/templates/platforms/ rather than "
                f"shipping an install that is silently missing it."
            )
        parts.append(f"\n\n---\n\n## Reference: {n}\n\n{p.read_text(encoding='utf-8', errors='replace')}\n")
    return "".join(parts)


def copy_section(src: str, dst: Path, *, force: bool) -> int:
    """Copy a directory section. Returns the number of files copied."""
    src_path = REPO_ROOT / src
    if not src_path.exists():
        return 0
    n = 0
    for p in src_path.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(src_path)
        target = dst / src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            continue
        shutil.copy2(p, target)
        n += 1
    return n


# ---------- Install strategies -------------------------------------------

def install_full(cfg: dict, target_root: Path, *, force: bool, dry_run: bool) -> dict:
    """Full skill install: SKILL.md + sections."""
    fs = cfg["folderStructure"]
    skill_dir = target_root / fs["skillPath"]
    skill_file = skill_dir / fs["filename"]

    body = read_skill_body()
    frontmatter = build_frontmatter(cfg.get("frontmatter"))
    content = frontmatter + body

    plan = {"file": str(skill_file), "size": len(content), "sections": []}
    if dry_run:
        for sec in ("references", "tools", "data", "examples"):
            if cfg.get("sections", {}).get(sec):
                plan["sections"].append(sec)
        return plan

    skill_dir.mkdir(parents=True, exist_ok=True)
    if skill_file.exists() and not force:
        raise SystemExit(f"Refusing to overwrite {skill_file} — pass --force to override.")
    skill_file.write_text(content, encoding="utf-8", newline="\n")

    for sec in ("references", "tools", "data", "examples"):
        if cfg.get("sections", {}).get(sec):
            n = copy_section(sec, skill_dir, force=force)
            plan["sections"].append(f"{sec} ({n} files)")
    return plan


def install_rule(cfg: dict, target_root: Path, *, force: bool, dry_run: bool) -> dict:
    """Single rule file (Cursor / Windsurf / Continue) with embedded references."""
    fs = cfg["folderStructure"]
    rule_dir = target_root / fs["skillPath"]
    rule_file = rule_dir / fs["filename"]

    body = read_skill_body()
    if cfg.get("embedReferences"):
        body = body + embed_references(cfg["embedReferences"])

    frontmatter = build_frontmatter(cfg.get("frontmatter"))
    content = frontmatter + body

    plan = {"file": str(rule_file), "size": len(content), "embedded": cfg.get("embedReferences", [])}
    if dry_run:
        return plan

    rule_dir.mkdir(parents=True, exist_ok=True)
    if rule_file.exists() and not force:
        raise SystemExit(f"Refusing to overwrite {rule_file} — pass --force to override.")
    rule_file.write_text(content, encoding="utf-8", newline="\n")
    return plan


def install_instructions_append(cfg: dict, target_root: Path, *, force: bool, dry_run: bool) -> dict:
    """Append a fenced section to copilot-instructions.md (idempotent)."""
    fs = cfg["folderStructure"]
    target = target_root / fs["projectRoot"] / fs["filename"]
    begin = cfg["appendMarker"]
    end = cfg["appendMarkerEnd"]

    body = read_skill_body()
    if cfg.get("embedReferences"):
        body = body + embed_references(cfg["embedReferences"])
    section = f"\n\n{begin}\n## WP Elementor Ops Skill\n\n{body}\n{end}\n"

    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    # Strip any prior fenced block, then append.
    if begin in existing and end in existing:
        before = existing.split(begin, 1)[0].rstrip()
        after = existing.split(end, 1)[1].lstrip()
        new_content = (before + "\n" + after).strip() + section
    else:
        new_content = (existing.rstrip() + section).lstrip("\n")

    plan = {"file": str(target), "size": len(new_content), "appended": True}
    if dry_run:
        return plan

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_content, encoding="utf-8", newline="\n")
    return plan


def install_zip_upload(cfg: dict, target_root: Path, *, force: bool, dry_run: bool) -> dict:
    """Bundle the skill as a zip for Claude.ai manual upload."""
    fs = cfg["folderStructure"]
    out_zip = target_root / fs["skillPath"]

    body = read_skill_body()
    frontmatter = build_frontmatter(cfg.get("frontmatter"))
    skill_content = frontmatter + body

    plan = {"file": str(out_zip), "size": 0, "entries": []}
    if dry_run:
        plan["entries"].append("SKILL.md (rewritten with platform frontmatter)")
        for sec in ("references", "data", "examples"):
            if cfg.get("sections", {}).get(sec):
                plan["entries"].append(f"{sec}/")
        return plan

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists() and not force:
        raise SystemExit(f"Refusing to overwrite {out_zip} — pass --force to override.")

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("elementor-headless/SKILL.md", skill_content)
        plan["entries"].append("elementor-headless/SKILL.md")
        for sec in ("references", "data", "examples"):
            if not cfg.get("sections", {}).get(sec):
                continue
            sec_root = REPO_ROOT / sec
            for p in sec_root.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(REPO_ROOT)
                    zf.write(p, arcname=f"elementor-headless/{rel.as_posix()}")
                    plan["entries"].append(f"elementor-headless/{rel.as_posix()}")
    plan["size"] = out_zip.stat().st_size
    return plan


STRATEGIES = {
    "full": install_full,
    "rule": install_rule,
    "instructions-append": install_instructions_append,
    "zip-upload": install_zip_upload,
}


# ---------- CLI -----------------------------------------------------------

def cmd_list() -> int:
    plats = list_platforms()
    if not plats:
        print("No platforms configured.", file=sys.stderr)
        return 1
    print(f"{'platform':<14} {'install type':<22} verified  as-of        display name")
    print("-" * 90)
    for p in plats:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        verified = "yes" if cfg.get("verified") else "no "
        as_of = cfg.get("verifiedAsOf", "?")
        print(f"{cfg['platform']:<14} {cfg['installType']:<22} {verified:<8}  {as_of:<12} {cfg['displayName']}")
    return 0


def cmd_info(name: str) -> int:
    cfg = load_platform(name)
    print(f"Platform: {cfg['platform']}  ({cfg['displayName']})")
    print(f"Install type: {cfg['installType']}")
    fs = cfg["folderStructure"]
    print(f"Project path: {fs['projectRoot']}/{fs['skillPath']}/{fs['filename']}".replace("//", "/"))
    if fs.get("globalRoot"):
        print(f"Global path:  {fs['globalRoot']}/{fs['skillPath']}/{fs['filename']}".replace("//", "/"))
    print(f"Sections: {', '.join(k for k, v in cfg.get('sections', {}).items() if v)}")
    print(f"Verified: {cfg.get('verified', False)} (as of {cfg.get('verifiedAsOf', 'unknown')})")
    if cfg.get("verificationNote"):
        print(f"Note: {cfg['verificationNote']}")
    if cfg.get("fallback"):
        fb = cfg["fallback"]
        print(f"\nFallback path (if the primary convention doesn't apply to your version):")
        print(f"  {json.dumps(fb, ensure_ascii=False, indent=2)}")
    print(f"\n{cfg['loaderBehaviour']}")
    return 0


def cmd_install(name: str, *, target: Path | None, use_global: bool, force: bool, dry_run: bool) -> int:
    cfg = load_platform(name)
    fs = cfg["folderStructure"]

    if target is None:
        if use_global:
            if not fs.get("globalRoot"):
                print(f"{name} does not support global install; falling back to project scope.", file=sys.stderr)
                target_root = Path.cwd() / fs["projectRoot"]
            else:
                target_root = expand_path(fs["globalRoot"])
        else:
            if cfg["installType"] == "instructions-append":
                target_root = Path.cwd()
            elif fs.get("projectRoot"):
                target_root = Path.cwd() / fs["projectRoot"]
            else:
                target_root = Path.cwd()
    else:
        target_root = target

    strategy = STRATEGIES.get(cfg["installType"])
    if not strategy:
        print(f"Unknown install type: {cfg['installType']}", file=sys.stderr)
        return 1

    print(f"Installing elementor-headless -> {cfg['displayName']}{' (DRY RUN)' if dry_run else ''}")
    print(f"Target root: {target_root}")
    plan = strategy(cfg, target_root, force=force, dry_run=dry_run)
    print(f"  file: {plan['file']}")
    print(f"  size: {plan.get('size', 0):,} bytes")
    if plan.get("sections"):
        print(f"  sections: {', '.join(plan['sections'])}")
    if plan.get("embedded"):
        print(f"  embedded refs: {', '.join(plan['embedded'])}")
    if plan.get("entries"):
        print(f"  zip entries: {len(plan['entries'])}")
    print(f"\n{cfg['loaderBehaviour']}")
    if not cfg.get("verified"):
        print(f"\nNOTE: this platform's loader behaviour is unverified — see info.")
    if cfg.get("fallback"):
        print(f"NOTE: a fallback convention is documented for this platform — run --info {name} to see it.")
    if dry_run:
        print("\n(dry run; nothing written.)")
    return 0


def interactive_pick() -> str:
    plats = list_platforms()
    print("Select an AI platform:\n")
    for i, p in enumerate(plats, 1):
        cfg = json.loads(p.read_text(encoding="utf-8"))
        print(f"  {i}. {cfg['displayName']} ({cfg['platform']})")
    print()
    choice = input("Number (or platform key): ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(plats):
            return plats[idx].stem
    if (PLATFORMS_DIR / f"{choice}.json").exists():
        return choice
    raise SystemExit("No platform selected.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install elementor-headless into an AI platform.")
    ap.add_argument("platform", nargs="?", help="Platform key (run --list for options)")
    ap.add_argument("--list", action="store_true", help="List supported platforms")
    ap.add_argument("--info", metavar="PLATFORM", help="Show platform install details and exit")
    ap.add_argument("--to", metavar="DIR", help="Target directory (overrides default project/global path)")
    ap.add_argument("--global", dest="use_global", action="store_true", help="Install to user-global location (where supported)")
    ap.add_argument("-f", "--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--dry-run", action="store_true", help="Show plan without writing")
    args = ap.parse_args()

    if args.list:
        return cmd_list()
    if args.info:
        return cmd_info(args.info)

    name = args.platform or interactive_pick()
    target = expand_path(args.to)
    return cmd_install(name, target=target, use_global=args.use_global, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
