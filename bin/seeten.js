#!/usr/bin/env node
'use strict';

// SeeTen CLI —— 一条命令装好 skill + 备好 Python 依赖。
// 零 npm 依赖：只用 Node 内置模块，所以 `npx github:guomc9/SeeTen` 拉起来很快。

const E = require('../lib/env');
const cmd = require('../lib/commands');

const USAGE = `
${E.C.bold}seeten${E.C.reset} —— 张量表格绘制（SeeTen skill 的安装器 + 运行器）

用法：
  seeten init [--global] [--no-demo]   安装 skill、备好 Python 依赖，并跑通一份演示
  seeten draw <脚本.py> [输出.pptx]     用同一套环境跑你的绘制脚本
  seeten draw --demo [输出.pptx]        生成通用演示 deck
  seeten render <文件.pptx>             导出 PNG，逐页看版式（需要 WPS 或 LibreOffice）
  seeten doctor                        环境自检
  seeten help                          显示本帮助

示例：
  npx github:guomc9/SeeTen init        # 一行装好（不需要先发布到 npm）
  seeten draw my_page.py out.pptx
`;

function main(argv) {
  const [name, ...rest] = argv;
  const opts = {
    global: rest.includes('--global') || rest.includes('-g'),
    demo: !rest.includes('--no-demo'),
    cwd: process.cwd(),
  };
  const args = rest.filter((a) => !a.startsWith('-'));

  switch (name) {
    case 'init':
    case 'install':
      return cmd.init(opts);
    case 'draw':
    case 'd':
      return cmd.draw(rest);            // draw 自己认 --demo，这里不能先过滤
    case 'render':
    case 'r':
      return cmd.render(args);
    case 'doctor':
    case 'doc':
      return cmd.doctor();
    case 'help':
    case undefined:
    case '--help':
    case '-h':
      console.log(USAGE);
      return 0;
    case '--version':
    case '-v':
      console.log(require('../package.json').version);
      return 0;
    default:
      E.bad(`未知命令：${name}`);
      console.log(USAGE);
      return 1;
  }
}

process.exit(main(process.argv.slice(2)));
