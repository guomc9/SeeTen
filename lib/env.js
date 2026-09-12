'use strict';
// 环境探测与 Python 依赖准备。只用 Node 内置模块，零 npm 依赖。

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const IS_WIN = process.platform === 'win32';
const SKILL_NAME = 'seeten-draw';          // 必须与 SKILL.md 的 name 一致（小写连字符）
const HOME_DIR = path.join(os.homedir(), '.seeten');
const VENV_DIR = path.join(HOME_DIR, 'venv');
const PKG_ROOT = path.resolve(__dirname, '..');

// ---------------------------------------------------------------- 基础输出

const C = {
  reset: '\x1b[0m', dim: '\x1b[2m', bold: '\x1b[1m',
  green: '\x1b[32m', red: '\x1b[31m', yellow: '\x1b[33m', cyan: '\x1b[36m',
};
const ok = (m) => console.log(`${C.green}✓${C.reset} ${m}`);
const bad = (m) => console.log(`${C.red}✗${C.reset} ${m}`);
const warn = (m) => console.log(`${C.yellow}!${C.reset} ${m}`);
const info = (m) => console.log(`${C.dim}·${C.reset} ${m}`);
const head = (m) => console.log(`\n${C.bold}${m}${C.reset}`);

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, {
    encoding: 'utf8',
    stdio: opts.inherit ? 'inherit' : 'pipe',
    ...opts,
  });
  return { code: r.status, out: (r.stdout || '').trim(), err: (r.stderr || '').trim() };
}

// ---------------------------------------------------------------- Python

function pythonCandidates() {
  if (IS_WIN) return [['python', []], ['py', ['-3']], ['python3', []]];
  return [['python3', []], ['python', []]];
}

/** 找一个可用的 Python 解释器；返回 {cmd, args, version} 或 null。 */
function findPython() {
  for (const [cmd, args] of pythonCandidates()) {
    const r = run(cmd, [...args, '-c', 'import sys;print(sys.version.split()[0])']);
    if (r.code === 0 && r.out) return { cmd, args, version: r.out };
  }
  return null;
}

function venvPython() {
  return IS_WIN
    ? path.join(VENV_DIR, 'Scripts', 'python.exe')
    : path.join(VENV_DIR, 'bin', 'python');
}

/** 解释器能不能 import pptx。 */
function hasPptx(py, args = []) {
  return run(py, [...args, '-c', 'import pptx,sys;sys.stdout.write("ok")']).code === 0;
}

/**
 * 拿到一个能跑 SeeTen 的 Python：
 *  1) 系统 Python 已经装了 python-pptx → 直接用，不动用户的机器；
 *  2) 否则在 ~/.seeten/venv 建虚拟环境并装 python-pptx（不污染系统环境）。
 * 返回 {cmd, args, source} 或 null。
 */
function ensurePython({ quiet = false } = {}) {
  const sys = findPython();
  if (!sys) return null;

  if (hasPptx(sys.cmd, sys.args)) {
    if (!quiet) ok(`Python ${sys.version}（系统环境已带 python-pptx）`);
    return { cmd: sys.cmd, args: sys.args, source: 'system' };
  }

  const vp = venvPython();
  if (fs.existsSync(vp) && hasPptx(vp)) {
    if (!quiet) ok(`复用已有虚拟环境 ${VENV_DIR}`);
    return { cmd: vp, args: [], source: 'venv' };
  }

  if (!quiet) info(`系统 Python ${sys.version} 没装 python-pptx，正在建独立环境…`);
  fs.mkdirSync(HOME_DIR, { recursive: true });
  const mk = run(sys.cmd, [...sys.args, '-m', 'venv', VENV_DIR]);
  if (mk.code !== 0) {
    bad('创建虚拟环境失败：' + (mk.err || mk.out));
    return null;
  }
  const pip = run(vp, ['-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
    '--upgrade', 'python-pptx']);
  if (pip.code !== 0) {
    bad('安装 python-pptx 失败：' + (pip.err || pip.out));
    return null;
  }
  if (!quiet) ok(`已建好独立环境并安装 python-pptx → ${VENV_DIR}`);
  return { cmd: vp, args: [], source: 'venv' };
}

// ---------------------------------------------------------------- 渲染器

/** 能不能把 pptx 导成 PNG（WPS 的 COM 接口，或 LibreOffice）。 */
function findRenderer() {
  if (IS_WIN) {
    const r = run('powershell', ['-NoProfile', '-Command',
      'if (Test-Path "HKCU:\\SOFTWARE\\Classes\\KWPP.Application") {"wps"} ' +
      'elseif (Test-Path "HKLM:\\SOFTWARE\\Classes\\KWPP.Application") {"wps"}']);
    if (r.out.includes('wps')) return { kind: 'wps', script: path.join(PKG_ROOT, 'scripts', 'render_deck.ps1') };
  }
  const lo = run(IS_WIN ? 'where' : 'which', ['soffice']);
  if (lo.code === 0 && lo.out) return { kind: 'libreoffice', cmd: lo.out.split(/\r?\n/)[0] };
  return null;
}

// ---------------------------------------------------------------- agent CLI

/** 探测当前目录/家目录里有哪些 agent CLI 的落点。 */
function detectTargets(cwd) {
  const found = [];
  const mk = (kind, dir) => ({ kind, dir });

  const projClaude = path.join(cwd, '.claude');
  const homeClaude = path.join(os.homedir(), '.claude');
  if (fs.existsSync(projClaude)) found.push(mk('claude-project', projClaude));
  else if (fs.existsSync(homeClaude)) found.push(mk('claude-home', homeClaude));

  for (const f of ['AGENTS.md', 'CLAUDE.md', 'KIMI.md']) {
    const p = path.join(cwd, f);
    if (fs.existsSync(p)) found.push(mk('instr', p));
  }
  return found;
}

const SEETEN_BLOCK = `
## Drawing conventions (SeeTen)

Before drawing tensor / tiling / scheduling diagrams or presentation pages, read
\`SKILL.md\` inside the SeeTen skill directory and follow its hard rules. Take style
parameters only from its \`assets/*.json\` and \`references/style-spec.md\`.
Generate pages with \`scripts/seeten_draw.py\` (run it through \`seeten draw\`).
`;

/** 往指令文件里幂等追加一段 SeeTen 指引。返回 true 表示写入了。 */
function appendInstr(file, skillDir) {
  let body = '';
  try { body = fs.readFileSync(file, 'utf8'); } catch { /* 新文件 */ }
  if (body.includes('Drawing conventions (SeeTen)')) return false;
  const rel = path.relative(path.dirname(file), skillDir).replace(/\\/g, '/') || '.';
  const block = SEETEN_BLOCK.replace('`SKILL.md`', `\`${rel}/SKILL.md\``)
    .replace('its `assets/', `its \`${rel}/assets/`)
    .replace('`references/style-spec.md`', `\`${rel}/references/style-spec.md\``)
    .replace('`scripts/seeten_draw.py`', `\`${rel}/scripts/seeten_draw.py\``);
  fs.appendFileSync(file, (body.endsWith('\n') || !body ? '' : '\n') + block, 'utf8');
  return true;
}

module.exports = {
  IS_WIN, SKILL_NAME, HOME_DIR, VENV_DIR, PKG_ROOT, C,
  ok, bad, warn, info, head, run,
  findPython, ensurePython, hasPptx, venvPython, findRenderer,
  detectTargets, appendInstr,
};
