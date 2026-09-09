#!/usr/bin/env node
/**
 * Install the elementor-headless skill into any of 8 supported AI platforms.
 *
 *   npx elementor-headless                       # interactive (arrow keys, zh-TW)
 *   npx elementor-headless --list
 *   npx elementor-headless claude-code --global
 *   npx elementor-headless cursor --to /path/to/project
 *   npx elementor-headless --dry-run claude-code
 *
 * Zero dependencies - colors, prompts and progress are hand-rolled so npx
 * starts instantly. Python is NOT needed to install, only to run the skill's
 * query/validation tools afterwards.
 *
 * Install types:
 *   full                - SKILL.md + references/ + tools/ + data/ + examples/
 *   rule                - single .md/.mdc rule file with embedded references
 *   instructions-append - fenced section appended to copilot-instructions.md
 *   zip-upload          - zip bundle for manual upload (Claude.ai)
 *
 * Exit codes: 0 = installed, 1 = failed, 2 = invocation error
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PLATFORMS = path.join(ROOT, "assets", "templates", "platforms");

// ---------- colors (hand-rolled chalk) -------------------------------------

const TTY = process.stdout.isTTY && !process.env.NO_COLOR && process.env.TERM !== "dumb";
const esc = (n) => (s) => (TTY ? `\x1b[${n}m${s}\x1b[0m` : s);
const bold = esc("1"), dim = esc("2");
const red = esc("1;31"), yellow = esc("1;33"), green = esc("1;32");
const cyan = esc("1;36"), blue = esc("1;34"), magenta = esc("1;35");
const gcyan = esc("36"), ggreen = esc("32");

const die = (msg, code = 1) => { console.error(red("error"), msg); process.exit(code); };
const info = (m) => console.log(blue("info"), m);
const warn = (m) => console.log(yellow("warn"), m);
const expand = (p) => (p && p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- the MOKSA banner ------------------------------------------------

const LETTERS = {
  M: ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
  O: [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
  K: ["██╗  ██╗", "██║ ██╔╝", "█████╔╝ ", "██╔═██╗ ", "██║  ██╗", "╚═╝  ╚═╝"],
  S: ["███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║", "╚══════╝"],
  A: [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
};
const PALETTE = [red, yellow, green, cyan, magenta];

function banner(subtitle) {
  console.log();
  for (let row = 0; row < 6; row++) {
    console.log("  " + [..."MOKSA"].map((ch, i) => PALETTE[i % PALETTE.length](LETTERS[ch][row])).join(" "));
  }
  console.log();
  console.log(bold(gcyan("               elementor-headless · Elementor 無頭建站技能包")));
  console.log(bold(yellow(`               ${subtitle}`)));
  console.log();
}

// ---------- the 完成 box ----------------------------------------------------

const visualWidth = (str) => {
  let w = 0;
  for (const ch of str.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "")) {
    const c = ch.codePointAt(0);
    w += (c >= 0x4e00 && c <= 0x9fff) || (c >= 0x3000 && c <= 0x303f) ||
         (c >= 0xff00 && c <= 0xffef) || (c >= 0xac00 && c <= 0xd7af) ? 2 : 1;
  }
  return w;
};

function box(lines, header = "  完成  ") {
  const width = Math.max(visualWidth(header), ...lines.map(visualWidth)) + 2;
  console.log();
  console.log(ggreen("╭" + "─".repeat(width) + "╮"));
  console.log(ggreen("│") + green(header) + " ".repeat(width - visualWidth(header)) + ggreen("│"));
  console.log(ggreen("├" + "─".repeat(width) + "┤"));
  for (const line of lines) {
    console.log(ggreen("│ ") + line + " ".repeat(Math.max(0, width - visualWidth(line) - 2)) + ggreen(" │"));
  }
  console.log(ggreen("╰" + "─".repeat(width) + "╯"));
  console.log();
}

// ---------- animated progress ----------------------------------------------

async function step(label, fn) {
  if (!TTY) { const out = await fn(); console.log(green("✔"), label); return out; }
  process.stdout.write(cyan("◐") + " " + label);
  const t0 = Date.now();
  const out = await fn();
  await sleep(Math.max(0, 140 - (Date.now() - t0)));
  process.stdout.write("\r" + green("✔") + " " + label + "\n");
  return out;
}

// ---------- interactive prompts (hand-rolled, zh-TW) ------------------------

function select(message, choices) {
  return new Promise((resolve) => {
    let idx = 0;
    const render = (first) => {
      if (!first) process.stdout.write(`\x1b[${choices.length + 1}A\x1b[J`);
      console.log(bold(message) + dim("（↑↓ 選擇，Enter 確定）"));
      choices.forEach((c, i) => {
        console.log(i === idx ? cyan(`  ❯ ${c.title}`) : `    ${c.title}`);
      });
    };
    render(true);
    readline.emitKeypressEvents(process.stdin);
    process.stdin.setRawMode(true);
    process.stdin.resume();
    const onKey = (_s, key) => {
      if (key.name === "up") idx = (idx - 1 + choices.length) % choices.length;
      else if (key.name === "down") idx = (idx + 1) % choices.length;
      else if (key.name === "return") {
        process.stdin.setRawMode(false);
        process.stdin.removeListener("keypress", onKey);
        process.stdin.pause();
        return resolve(choices[idx].value);
      } else if (key.name === "c" && key.ctrl) { process.stdin.setRawMode(false); process.exit(130); }
      else return;
      render(false);
    };
    process.stdin.on("keypress", onKey);
  });
}

function toggle(message, initial = false) {
  const yes = { title: initial ? "要（預設）" : "要", value: true };
  const no = { title: initial ? "不要" : "不要（預設）", value: false };
  return select(message, initial ? [yes, no] : [no, yes]);
}

// ---------- platform config ------------------------------------------------

function listPlatforms() {
  return fs.readdirSync(PLATFORMS).filter((f) => f.endsWith(".json")).sort()
    .map((f) => JSON.parse(fs.readFileSync(path.join(PLATFORMS, f), "utf8")));
}

function loadPlatform(name) {
  const p = path.join(PLATFORMS, `${name}.json`);
  if (!fs.existsSync(p)) die(`Unknown platform: ${name} — run --list to see options.`, 2);
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function detectPlatforms() {
  const cwd = process.cwd(), home = os.homedir();
  const hits = [];
  const probe = (dir, name) => { if (fs.existsSync(dir)) hits.push(name); };
  probe(path.join(cwd, ".claude"), "claude-code");
  probe(path.join(home, ".claude"), "claude-code");
  probe(path.join(cwd, ".cursor"), "cursor");
  probe(path.join(home, ".cursor"), "cursor");
  probe(path.join(cwd, ".github"), "copilot");
  probe(path.join(home, ".codex"), "codex-cli");
  probe(path.join(home, ".gemini"), "gemini-cli");
  probe(path.join(home, ".windsurf"), "windsurf");
  return [...new Set(hits)];
}

// ---------- content assembly ------------------------------------------------

function buildFrontmatter(fm) {
  if (!fm) return "";
  const lines = ["---"];
  for (const [k, v] of Object.entries(fm)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) lines.push(`${k}: [${v.map((x) => JSON.stringify(x)).join(", ")}]`);
    else if (typeof v === "boolean") lines.push(`${k}: ${v}`);
    else if (typeof v === "string" && (v.includes("\n") || v.length > 100)) {
      lines.push(`${k}: |`);
      for (const sub of v.split("\n")) lines.push(`  ${sub}`);
    } else lines.push(`${k}: ${JSON.stringify(v)}`);
  }
  lines.push("---");
  return lines.join("\n") + "\n\n";
}

function readSkillBody() {
  let raw = fs.readFileSync(path.join(ROOT, "SKILL.md"), "utf8");
  if (raw.startsWith("---")) {
    const end = raw.indexOf("\n---", 3);
    if (end !== -1) raw = raw.slice(end + 4).replace(/^\n+/, "");
  }
  return raw;
}

function embedReferences(names) {
  // A missing file is a hard error, not a skip - silently shipping a rule file
  // short one document is the silent-failure class this skill exists to kill.
  const parts = [];
  for (const n of names) {
    const p = path.join(ROOT, "references", n);
    if (!fs.existsSync(p)) {
      const avail = fs.readdirSync(path.join(ROOT, "references")).filter((q) => q.endsWith(".md")).join(", ");
      die(`Platform config asks to embed references/${n}, which does not exist.\nAvailable: ${avail}`);
    }
    parts.push(`\n\n---\n\n## Reference: ${n}\n\n${fs.readFileSync(p, "utf8")}\n`);
  }
  return parts.join("");
}

function walkFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.name === "__pycache__") continue;
    if (e.isDirectory()) out.push(...walkFiles(p));
    else out.push(p);
  }
  return out;
}

function copySection(sec, dstRoot, force) {
  // Upgrades MUST delete what the previous version left behind: a stale, wrong
  // dataset sitting next to the right one is worse than no installer.
  const srcPath = path.join(ROOT, sec);
  if (!fs.existsSync(srcPath)) return [0, 0];
  let copied = 0;
  const keep = new Set();
  for (const f of walkFiles(srcPath)) {
    const rel = path.relative(srcPath, f);
    const target = path.join(dstRoot, sec, rel);
    keep.add(path.resolve(target));
    fs.mkdirSync(path.dirname(target), { recursive: true });
    if (fs.existsSync(target) && !force) continue;
    fs.copyFileSync(f, target);
    copied++;
  }
  let pruned = 0;
  const secDir = path.join(dstRoot, sec);
  if (fs.existsSync(secDir)) {
    for (const f of walkFiles(secDir)) {
      if (!keep.has(path.resolve(f))) { fs.unlinkSync(f); pruned++; }
    }
  }
  return [copied, pruned];
}

// ---------- strategies -----------------------------------------------------

async function installFull(cfg, root, force, dry) {
  const fsr = cfg.folderStructure;
  const dir = path.join(root, fsr.skillPath);
  const file = path.join(dir, fsr.filename);
  const content = buildFrontmatter(cfg.frontmatter) + readSkillBody();
  const plan = { file, size: content.length, sections: [] };
  if (dry) {
    for (const s of ["references", "tools", "data", "examples"]) if (cfg.sections?.[s]) plan.sections.push(s);
    return plan;
  }
  await step("寫入 SKILL.md", () => {
    fs.mkdirSync(dir, { recursive: true });
    if (fs.existsSync(file) && !force) die(`Refusing to overwrite ${file} - pass --force.`);
    fs.writeFileSync(file, content);
  });
  for (const s of ["references", "tools", "data", "examples"]) {
    if (!cfg.sections?.[s]) continue;
    await step(`複製 ${s}/`, () => {
      const [n, pruned] = copySection(s, dir, force);
      plan.sections.push(`${s} (${n} files${pruned ? `, ${pruned} stale removed` : ""})`);
    });
  }
  await step("驗證安裝", () => {
    if (!fs.existsSync(file)) die("install verification failed: SKILL.md missing");
    if (cfg.sections?.data && !fs.existsSync(path.join(dir, "data", "elementor-schema.json")))
      die("install verification failed: data/elementor-schema.json missing");
  });
  return plan;
}

async function installRule(cfg, root, force, dry) {
  const fsr = cfg.folderStructure;
  const file = path.join(root, fsr.skillPath, fsr.filename);
  let body = readSkillBody();
  if (cfg.embedReferences) body += embedReferences(cfg.embedReferences);
  const content = buildFrontmatter(cfg.frontmatter) + body;
  const plan = { file, size: content.length, embedded: cfg.embedReferences || [] };
  if (dry) return plan;
  await step("寫入 rule 檔（內嵌參考文件）", () => {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    if (fs.existsSync(file) && !force) die(`Refusing to overwrite ${file} - pass --force.`);
    fs.writeFileSync(file, content);
  });
  return plan;
}

async function installAppend(cfg, root, force, dry) {
  const fsr = cfg.folderStructure;
  const target = path.join(root, fsr.projectRoot, fsr.filename);
  const { appendMarker: begin, appendMarkerEnd: end } = cfg;
  let body = readSkillBody();
  if (cfg.embedReferences) body += embedReferences(cfg.embedReferences);
  const section = `\n\n${begin}\n## Headless Elementor Skill\n\n${body}\n${end}\n`;
  const existing = fs.existsSync(target) ? fs.readFileSync(target, "utf8") : "";
  let content;
  if (existing.includes(begin) && existing.includes(end)) {
    const before = existing.split(begin)[0].replace(/\s+$/, "");
    const after = existing.split(end).slice(1).join(end).replace(/^\s+/, "");
    content = (before + "\n" + after).trim() + section;
  } else {
    content = (existing.replace(/\s+$/, "") + section).replace(/^\n+/, "");
  }
  const plan = { file: target, size: content.length, appended: true };
  if (dry) return plan;
  await step("附加到 copilot-instructions.md", () => {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content);
  });
  return plan;
}

async function installZip(cfg, root, force, dry) {
  // Node has no built-in zip. Stage the folder, then use whatever archiver the
  // OS has; if none, the staged folder + instructions are the result.
  const fsr = cfg.folderStructure;
  const outZip = path.join(root, fsr.skillPath);
  const stage = path.join(root, "elementor-headless-stage", "elementor-headless");
  const plan = { file: outZip, size: 0, entries: [] };
  if (dry) { plan.entries.push("SKILL.md + sections (staged, then zipped)"); return plan; }
  await step("打包 zip（Claude.ai 手動上傳用）", () => {
    fs.rmSync(path.dirname(stage), { recursive: true, force: true });
    fs.mkdirSync(stage, { recursive: true });
    fs.writeFileSync(path.join(stage, "SKILL.md"), buildFrontmatter(cfg.frontmatter) + readSkillBody());
    for (const s of ["references", "data", "examples"]) {
      if (cfg.sections?.[s]) copySection(s, stage, true);
    }
    if (fs.existsSync(outZip) && !force) die(`Refusing to overwrite ${outZip} - pass --force.`);
    fs.mkdirSync(path.dirname(outZip), { recursive: true });
    try {
      if (process.platform === "win32") {
        execFileSync("powershell", ["-NoProfile", "-Command",
          `Compress-Archive -Path '${stage}' -DestinationPath '${outZip}' -Force`]);
      } else {
        execFileSync("zip", ["-qr", outZip, "elementor-headless"], { cwd: path.dirname(stage) });
      }
      fs.rmSync(path.dirname(stage), { recursive: true, force: true });
      plan.size = fs.statSync(outZip).size;
    } catch {
      plan.file = path.dirname(stage);
      plan.note = `no zip tool found - folder staged at ${path.dirname(stage)}; zip it manually`;
    }
  });
  return plan;
}

const STRATEGIES = {
  full: installFull, rule: installRule,
  "instructions-append": installAppend, "zip-upload": installZip,
};

// ---------- CLI ------------------------------------------------------------

function cmdList() {
  const rows = listPlatforms();
  console.log(`${"platform".padEnd(14)} ${"install type".padEnd(22)} verified  as-of        display name`);
  console.log("-".repeat(90));
  for (const c of rows) {
    console.log(`${c.platform.padEnd(14)} ${c.installType.padEnd(22)} ${(c.verified ? "yes" : "no ").padEnd(8)}  ${(c.verifiedAsOf || "?").padEnd(12)} ${c.displayName}`);
  }
}

function cmdInfo(name) {
  const c = loadPlatform(name);
  const f = c.folderStructure;
  console.log(`Platform: ${c.platform}  (${c.displayName})`);
  console.log(`Install type: ${c.installType}`);
  console.log(`Project path: ${[f.projectRoot, f.skillPath, f.filename].filter(Boolean).join("/")}`);
  if (f.globalRoot) console.log(`Global path:  ${[f.globalRoot, f.skillPath, f.filename].filter(Boolean).join("/")}`);
  console.log(`Verified: ${!!c.verified} (as of ${c.verifiedAsOf || "unknown"})`);
  console.log(`\n${c.loaderBehaviour}`);
}

async function main() {
  const argv = process.argv.slice(2);
  const flags = new Set(argv.filter((a) => a.startsWith("--") || a === "-f"));
  const pos = argv.filter((a) => !a.startsWith("-") && argv[argv.indexOf(a) - 1] !== "--to" && argv[argv.indexOf(a) - 1] !== "--info");
  const getOpt = (name) => { const i = argv.indexOf(name); return i !== -1 ? argv[i + 1] : null; };

  if (flags.has("--list")) return cmdList();
  if (getOpt("--info")) return cmdInfo(getOpt("--info"));

  let name = pos[0];
  let useGlobal = flags.has("--global");
  let force = flags.has("--force") || flags.has("-f");
  const dry = flags.has("--dry-run");

  // Interactive mode: no platform named, and a real terminal to ask in.
  if (!name && process.stdin.isTTY && process.stdout.isTTY) {
    banner("Skill Installer");
    const detected = detectPlatforms();
    if (detected.length) info(`偵測到：${detected.map((d) => cyan(d)).join("、")}`);
    const plats = listPlatforms();
    name = await select("你想裝在哪個 AI 助手？", plats.map((c) => ({
      title: `${c.displayName}${detected.includes(c.platform) ? green("  ●") : ""}`,
      value: c.platform,
    })));
    const cfgPeek = loadPlatform(name);
    if (cfgPeek.folderStructure.globalRoot && cfgPeek.installType !== "zip-upload") {
      useGlobal = await toggle("要全域安裝嗎？（所有專案都能用）", detected.includes(name));
    }
    force = await toggle("檔案如果已經存在要覆蓋嗎？", true);
  } else if (!name) {
    cmdList();
    console.log("\nUsage: npx elementor-headless <platform> [--global] [--to DIR] [--force] [--dry-run]");
    return;
  } else {
    banner("Skill Installer");
  }

  const cfg = loadPlatform(name);
  const fsr = cfg.folderStructure;
  let root = getOpt("--to") ? path.resolve(expand(getOpt("--to"))) : null;
  if (!root) {
    if (useGlobal && fsr.globalRoot) root = expand(fsr.globalRoot);
    else if (cfg.installType === "instructions-append") root = process.cwd();
    else root = path.join(process.cwd(), fsr.projectRoot || "");
  }

  info(`Installing elementor-headless → ${cyan(cfg.displayName)}${useGlobal ? dim("（全域）") : ""}${dry ? yellow("（DRY RUN）") : ""}`);
  info(`Target: ${dim(root)}`);
  console.log();
  const plan = await STRATEGIES[cfg.installType](cfg, root, force, dry);

  const lines = [
    `${bold("平台")}　${cfg.displayName}`,
    `${bold("檔案")}　${plan.file}`,
    `${bold("大小")}　${plan.size.toLocaleString()} bytes`,
  ];
  if (plan.sections?.length) lines.push(`${bold("內容")}　${plan.sections.join(", ")}`);
  if (plan.embedded?.length) lines.push(`${bold("內嵌")}　${plan.embedded.join(", ")}`);
  if (plan.note) lines.push(yellow(`NOTE　${plan.note}`));
  lines.push("");
  lines.push(dim("下一步：對你的 AI 助手描述一個頁面，讓它跑 el.py 查證後動手。"));
  box(lines, dry ? "  DRY RUN  " : "  完成  ");
  if (dry) console.log(dim("(dry run; nothing written.)"));
  console.log(dim(cfg.loaderBehaviour));
}

main();
