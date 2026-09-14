'use strict';
// seeten 的四条命令：init / draw / render / doctor

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const E = require('./env');
const { C, ok, bad, warn, info, head, run, PKG_ROOT, SKILL_NAME } = E;

const SKILL_CONTENT = [
  'SKILL.md', 'README.md', 'README.zh-CN.md',
  'references', 'scripts', 'assets', 'examples', 'cases',
];

// ---------------------------------------------------------------- init

function copySkill(dest) {
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  for (const item of SKILL_CONTENT) {
    const src = path.join(PKG_ROOT, item);
    if (!fs.existsSync(src)) continue;
    fs.cpSync(src, path.join(dest, item), {
      recursive: true,
      filter: (s) => !/[\\/](_render|__pycache__)[\\/]?$/.test(s) && !s.endsWith('.pyc'),
    });
  }
}

function init({ cwd = process.cwd(), global: isGlobal = false, demo = true } = {}) {
  head('SeeTen 安装');

  // 1) 找落点
  const targets = E.detectTargets(cwd);
  const claudeTarget = targets.find((t) => t.kind.startsWith('claude'));
  let skillDir = null;

  if (isGlobal) {
    skillDir = path.join(require('node:os').homedir(), '.claude', 'skills', SKILL_NAME);
  } else if (claudeTarget && claudeTarget.kind === 'claude-project') {
    skillDir = path.join(claudeTarget.dir, 'skills', SKILL_NAME);
  } else if (claudeTarget) {
    skillDir = path.join(claudeTarget.dir, 'skills', SKILL_NAME);
  } else {
    skillDir = path.join(cwd, '.claude', 'skills', SKILL_NAME);
    warn('没检测到 .claude 目录，按项目级安装到当前目录');
  }

  copySkill(skillDir);
  ok(`skill 已安装 → ${skillDir}`);

  // 2) 指令文件（AGENTS.md / CLAUDE.md / KIMI.md）
  for (const t of targets.filter((x) => x.kind === 'instr')) {
    if (E.appendInstr(t.dir, skillDir)) ok(`已往 ${path.basename(t.dir)} 追加 SeeTen 指引`);
    else info(`${path.basename(t.dir)} 里已有 SeeTen 指引，跳过`);
  }

  // 3) Python 依赖
  const py = E.ensurePython();
  if (!py) {
    bad('没找到可用的 Python（需要 3.8+）。装好 Python 后重跑 `seeten init`');
    return 1;
  }

  // 4) 跑通一份 demo，顺带做版心自检
  if (demo) {
    const out = path.join(skillDir, 'examples', '_smoke.pptx');
    const r = run(py.cmd, [...py.args, path.join(skillDir, 'scripts', 'seeten_draw.py'), out]);
    const line = (r.out || '').split(/\r?\n/).find((l) => l.includes('版心'));
    if (r.code === 0 && line && /0 越界 \/ 0 重叠/.test(line)) {
      ok(`跑通演示：${line.trim()}`);
      fs.rmSync(out, { force: true });
    } else {
      warn('演示生成没完全通过，输出：' + (r.out || r.err || '').split(/\r?\n/).slice(-3).join(' | '));
    }
  }

  // 5) 渲染器（可选能力）
  const rend = E.findRenderer();
  if (rend) ok(`渲染预览可用（${rend.kind}）`);
  else warn('没找到 WPS 或 LibreOffice —— 生成 pptx 没问题，但"导出 PNG 看图"这步用不了');

  head('好了，接下来');
  if (claudeTarget) {
    console.log('  Claude Code：直接说需求即可被自动匹配，或显式调用 /seeten-draw');
  }
  const rel = path.relative(cwd, skillDir);
  const shown = (rel && !rel.startsWith('..')) ? rel : skillDir;
  console.log(`  其它 CLI：把 ${shown.split(path.sep).join('/')}/SKILL.md 指给它`);
  console.log('  自己写页面：');
  console.log(`    ${C.cyan}seeten draw my_page.py out.pptx${C.reset}   # 用同一套环境跑你的脚本`);
  console.log(`    ${C.cyan}seeten render out.pptx${C.reset}            # 导出 PNG 逐页看图`);
  return 0;
}

// ---------------------------------------------------------------- draw

function draw(args) {
  const positional = args.filter((a) => !a.startsWith('-'));
  const wantDemo = args.includes('--demo');
  const script = positional[0];
  if (!wantDemo && !script) {
    bad('用法：seeten draw <脚本.py> [输出.pptx]   （或 seeten draw --demo out.pptx）');
    return 1;
  }
  const py = E.ensurePython({ quiet: true });
  if (!py) { bad('没有可用的 Python，先跑 `seeten init`'); return 1; }

  const scriptsDir = path.join(PKG_ROOT, 'scripts');
  const env = {
    ...process.env,
    PYTHONPATH: [scriptsDir, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };

  const cmdArgs = wantDemo
    ? [path.join(scriptsDir, 'seeten_draw.py'), script || 'demo.pptx']
    : [path.resolve(script), ...positional.slice(1)];
  const r = spawnSync(py.cmd, [...py.args, ...cmdArgs], { stdio: 'inherit', env });
  return r.status ?? 1;
}

// ---------------------------------------------------------------- render

function render(args) {
  const pptx = args[0];
  if (!pptx || !fs.existsSync(pptx)) {
    bad('用法：seeten render <文件.pptx>   （需要本机有 WPS 或 LibreOffice）');
    return 1;
  }
  const r = E.findRenderer();
  if (!r) {
    bad('没找到 WPS 或 LibreOffice。装任一个即可导出 PNG 看图');
    return 1;
  }
  if (r.kind === 'wps') {
    const p = spawnSync('powershell', ['-NoProfile', '-File', r.script, path.resolve(pptx)],
      { stdio: 'inherit' });
    return p.status ?? 1;
  }
  const outDir = path.join(path.dirname(path.resolve(pptx)), '_render');
  fs.mkdirSync(outDir, { recursive: true });
  const p = spawnSync(r.cmd, ['--headless', '--convert-to', 'png', '--outdir', outDir, path.resolve(pptx)],
    { stdio: 'inherit' });
  if (p.status === 0) ok(`导出到 ${outDir}`);
  return p.status ?? 1;
}

// ---------------------------------------------------------------- doctor

function doctor() {
  head('SeeTen 环境自检');
  const sys = E.findPython();
  sys ? ok(`Python ${sys.version}  (${sys.cmd})`) : bad('没找到 Python（需要 3.8+）');

  if (sys && E.hasPptx(sys.cmd, sys.args)) ok('系统 Python 已带 python-pptx');
  else if (fs.existsSync(E.venvPython()) && E.hasPptx(E.venvPython())) ok(`独立环境可用 → ${E.VENV_DIR}`);
  else warn('python-pptx 未就绪（跑 `seeten init` 会自动装到 ' + E.VENV_DIR + '）');

  const py = (sys && E.hasPptx(sys.cmd, sys.args)) ? [sys.cmd, sys.args]
    : (fs.existsSync(E.venvPython()) && E.hasPptx(E.venvPython()) ? [E.venvPython(), []]
      : null);
  if (py && E.hasModule(py[0], py[1], 'matplotlib')) {
    ok('matplotlib 已就绪（性能对比图走贴图渲染）');
  } else if (py) {
    warn('matplotlib 未就绪：性能对比图会退回原生柱状图（pip install matplotlib）');
  }

  const rend = E.findRenderer();
  rend ? ok(`渲染预览可用（${rend.kind}）`) : warn('没有 WPS / LibreOffice，无法导出 PNG 看版式');

  const targets = E.detectTargets(process.cwd());
  if (targets.length) targets.forEach((t) => info(`检测到 ${t.kind}: ${t.dir}`));
  else info('当前目录没检测到 .claude / AGENTS.md 等落点（init 会装到 ./.claude/skills）');

  const installed = [
    path.join(process.cwd(), '.claude', 'skills', SKILL_NAME),
    path.join(require('node:os').homedir(), '.claude', 'skills', SKILL_NAME),
  ].filter((p) => fs.existsSync(path.join(p, 'SKILL.md')));
  installed.forEach((p) => ok(`skill 已安装 → ${p}`));
  if (!installed.length) warn('skill 还没装（跑 `seeten init`）');
  return 0;
}

module.exports = { init, draw, render, doctor };
