# pptx 页面 → 图片（文档配图的真渲染管线）

文档里的"页面截图"必须来自**真正的 Office 渲染器**。

## 为什么不能自己复刻

用 python-pptx 读形状再用 matplotlib 重画（"复刻层"）会系统性丢东西：
**Connector/箭头**（坐标轴箭头等）、**非默认字体**（Consolas 等被替换）、
**特殊字形**（↪ / ⚠ 显示为方框）。曾用复刻层画了一版调度页，箭头与字体全丢、
返工重画——配图一律走真渲染。

## 安装（免 root 的便携方案）

| 组件 | 做法 |
|---|---|
| LibreOffice | 下载官方推荐的 AppImage（如 libreitalia 的 `LibreOffice-latest.basic-x86_64.AppImage`），`mv` 到固定工具目录，`chmod +x`，`./xxx.AppImage --appimage-extract` 解压出 `squashfs-root/`，入口是 `squashfs-root/AppRun`（免 FUSE、免 root） |
| CJK 字体 | 把 `NotoSansCJKsc-Regular.otf`（或 HeiTi.ttf）放进 `~/.local/share/fonts/`，`fc-cache -f`；**不装字体渲染中文全是方框** |
| PDF → PNG | `pip install PyMuPDF` |

> conda-forge 没有 libreoffice 包；`snap install` 需要 root —— 便携 AppImage 是本
> 环境唯一可行的路线。`render_pptx.py` 会自动探测 `$OP_DESIGN_DOC_LO` 或
> /data/g00977778/tools/squashfs-root/AppRun 等常见位置。

## 转换命令（render_pptx.py 已封装）

```bash
cd <tools>
./squashfs-root/AppRun --headless \
  -env:UserInstallation=file:///tmp/lo-profile \
  --convert-to pdf --outdir <outdir> <file.pptx>
```

```bash
# 选页 + 裁剪 + 导出 PNG（一键）
python scripts/render_pptx.py deck.pptx --pages 2,3 --dpi 140 --outdir figs/
python scripts/render_pptx.py deck.pptx --pages 5 --crop 0.62,1.72,13.95,4.02 --out figs/barrier.png
```

## 配图来源：先改 pptx、再渲染（不要给 PNG 打补丁）

需要"去掉标题里的页号"等调整时，**拷贝源 pptx 到工作目录、用 python-pptx 改文档
本身、再统一渲染**。曾经图省事在白底 PNG 上打白块遮盖页号，把标题第一个词的边缘
也盖掉了。现成脚本：

```bash
python scripts/pptx_tweaks.py in.pptx out.pptx --strip-title-numbers --bold-white-on-dark
```

- 去标题页号：对 `font.size >= 28` 的 run 做 `re.sub(r"^\d+\.\s*", "", text)`；
- 蓝格白字加粗：单元格为深色底且 run 为白色时 `font.bold = True`（渲染更清晰）。

## 裁剪（用 PyMuPDF 的 clip）

- 页面在 PDF 里是 72 点/英寸：`clip=Rect(x0*72, y0*72, x1*72, y1*72)`；
- 裁剪区从 pptx 形状几何读出（EMU → 英寸）再换算；裁"标题 + 表格 + 注记"，
  不留大片空白（表底 = 表顶 + 行高 × 行数，注记再加 0.4~0.6in）；
- 多页导出用 `get_pixmap(matrix=Matrix(dpi/72, dpi/72), clip=...)`。

## 常见坑

- 首跑必须给 `-env:UserInstallation=file:///tmp/lo-profile`（否则写配置失败）；
- 渲染前 `fc-list | grep -i noto` 验证字体；缺字表现为方框而非报错；
- slide 序号 0-based；算法页/例子页常成对出现，先列形状清单再决定取哪几页；
- 嵌入 pptx 的 matplotlib 图（性能柱状图等）可以**直接从 pptx 抽原图**：
  `sh.shape_type == PICTURE` → `sh.image.blob`，比截屏更清晰。 


## 版式细节（实践补充）

### 页号可能是多段的

标题形如 `2.1. 机制① …`（段号）或 `2. Dense Swizzle`（页号）都存在。剥离正则用
**多段形式**：`^(?:\d+\.)+\s*`（只写 `^\d+\.` 会把 "2.1." 剥成 "1."，
残留一个错位的段号）。剥离后**回读标题文本确认干净**再渲染。

### 同一文档内配图要统一版式

多张页面图放进同一篇文档时，建议统一为"**内容版式**"：裁掉页大标题与标签胶囊，
保留小节标题（如"① idle-core trim…"）与底部注记——嵌进正文后不会出现
"页标题与文档章节冲突""上半张有标题下半张没有"这类不齐整感。

### 裁剪公式

- 表底 ≈ 表顶 + 行高 × 行数（从 pptx 取行高，EMU→英寸）；
- 注记在表底 + 0.1~0.2in 起，通常 1~2 行，裁到表底 + 0.6in 内；
- 裁剪区从形状几何起点（最小值）向外留 0.1~0.15in 边距；
- 用 `render_pptx.py --crop x0,y0,x1,y1`（英寸）；渲染后立即回看确认没有截断。

### 修改版 pptx 留档

修改后的 pptx（去页号/加粗版）存到文档目录的 `src/` 下，命名带 `-mod` 后缀——
配图可复现、也能对照原始文件核对差异。
