# 项目注意事项

## 架构

- VitePress 静态站点，`doc/` 为源目录
- 公众号文章存档流程：`wechat-archive-tool/` 下载 → `doc/public/wechat/articles/` → `scripts/optimize_wechat.py` 优化 → VitePress 构建
- 文章目录页：`doc/wechat.md`（VitePress Vue SFC），独立首页：`doc/public/wechat/browse.html`（下载器生成）
- 文章数据流：`wechat.data.js` 数据加载器 → `wechat.md` Vue 组件渲染

## 下载器 (`wechat-archive-tool/`)

- 入口：`python main.py`（需 Playwright + 微信登录 Cookie）
- 配置文件 `config.json` 路径相对于工具目录
- `_clean_html()` 在 `src/downloader.py` 中负责清理 WeChat 页面垃圾
- 视频下载默认开启，文件较大（单个 30MB+），GitHub Pages 放不下时关掉
- 下载后必须运行 `scripts/optimize_wechat.py` 优化（图片压缩、CSS 去重、HTML 压缩、元数据生成）

### 单篇文章下载注意事项

- 使用 `download_single.py` 下载单篇时，**必须依次调用**（顺序不可颠倒）：
  1. `dl._fix_image_urls(soup)`
  2. **`await dl._inline_css(soup)`**（将外部 CSS 拉取内联，否则 `_clean_html` 会删除 link 导致样式丢失）
  3. `dl._clean_html(soup)`
  - 注意：`_inline_css` 是 async 方法，需要 `await`
- 删除旧目录时**只删同名目录**，禁止 `glob(f'{date}_*')` 通配删除，否则会误删同日期其他文章
- 下载完成后必须运行优化脚本：`python scripts/optimize_wechat.py`（至少执行 CSS 去重 + HTML 压缩 + 元数据生成三步）
- 修改过 `_clean_html()` 或下载器源码后，受影响的文章需重新下载才能生效
- `protected_articles` 列表（`config.json`）记录手动修改过的文章目录，避免误操作覆盖

### 自定义重下载脚本注意事项

编写类似 `restore_275.py` / `dl_gaoxiaolianmeng.py` 的单篇重下载脚本时，以下陷阱必须避免：

#### 目录匹配必须精确

同一日期有多篇文章共存时，`find_dir` 必须使用足够具体的子串，避免误匹配其他文章：

```python
# ❌ 危险：'高校联盟赛' 匹配到 2021、2025 等多篇同关键词文章
article_dir = find_dir('高校联盟赛')

# ✅ 安全：使用标题中的独特部分
article_dir = find_dir('内地站日程')  # 只有 2025 这篇
```

**验证方法**：首次运行后检查打印的 `Article dir: xxx` 是否为目标目录。

#### js_content 空值检查对 SVG 图文文章无效

SVG 图文型文章（如 iPaiban 编辑器制作的文章）的 `#js_content` 内全是 `<svg>` 和 `<section>`，无可见文本节点。`get_text(strip=True)` 返回空字符串，导致误判为"页面加载失败"：

```python
# ❌ SVG 图文文章会返回 0，误判为 CAPTCHA/失败
if not js or len(js.get_text(strip=True)) < 50:
    return False

# ✅ 检查 HTML 长度或子元素数量
if not js or len(str(js)) < 2000:
    return False
```

#### og:image 属性顺序因模板而异

模板 head 中 og:image 的 `property` 和 `content` 属性顺序可能是 `content="..." property="og:image"`（content 在前），正则必须覆盖两种顺序：

```python
# ❌ 只匹配 property 在 content 之前的格式
re.sub(r'(og:image[^>]+content=)"[^"]*"', r'\1"cover.jpg"', html)

# ✅ 同时匹配两种顺序
re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', html)
```

#### 文件名参数污染（URL query string 拼入文件名）

URL 替换后容易把 `&tp=webp&wxfrom=15&wx_lazy=1` 等查询参数拼到本地文件名里，导致文件找不到。替换后必须清理：

```python
result = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', result)
result = re.sub(r'(rem_\d+\.\w+)&[^"\s]+', r'\1', result)
```

#### 下载后清理旧未引用图片

重新下载会产生新的 `img_*` 文件，模板 head 替换后旧文章独有的 `rem_*` 文件不再被引用。应将 HTML 中不引用的 `.jpg/.png/.gif/.webp` 文件删除，避免目录膨胀。

#### MP 后端搜索获取文章 URL

如果只有文章标题、不知原始 URL，可通过 MP 后端 API 搜索：

```python
from urllib.parse import quote
token = re.search(r'token=(\d+)', page.url).group(1)
query = quote('文章标题关键词')
api_url = f'https://mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex&begin=0&count=50&type=9&query={query}&token={token}&lang=zh_CN&f=json'
resp = await page.evaluate(f"async () => {{ const r = await fetch('{api_url}'); return await r.text(); }}")
data = json.loads(resp)
# data['app_msg_list'] 中每条含 title、link、create_time
```

**搜索关键词需 URL-encode**（`urllib.parse.quote`），否则中文乱码导致 0 结果。

#### `post_process.py` 类型检测误判陷阱

`detect_type()` 在整个 HTML 字符串中搜索 `share_content_page` 和 `share_content_page_bd`，但 WeChat 框架 CSS 中也包含这些 class 名。导致 body class 为 `mm_appmsg` 的标准文章被误判为 `share_content_page`，从而应用错误的参考 head，页面样式炸裂。

```python
# ❌ 当前实现：在整个 HTML（含 CSS）中搜索，会误判
def detect_type(html):
    if 'share_content_page' in html and 'share_content_page_bd' in html:
        return 'share_content_page'
    return 'appmsg'

# ✅ 修复方向：只在 body 内容区域搜索，排除 head 中的 CSS
```

**已知误判案例**：`2025-03-24_2025高校联盟赛内地站日程与参赛名单公布` 文章（body class 为 `mm_appmsg`）被误判为 `share_content_page`，导致用错了参考文章 `2024-11-26_小雪伊始` 的 head，样式完全错误。

**临时解决**：对 body class 含 `mm_appmsg` 的文章，手动用 `appmsg` 模板（`2024-12-15_冬日畅言`）替换 head，跳过 `post_process.py`。

#### DOCTYPE 重复陷阱

`post_process.py` 的 `fix_share_content_page()` 和 `fix_appmsg()` 返回值格式为：
```python
return '<!DOCTYPE html>\n' + new_head + '</head>\n' + body_tag + body_content
```

但 `new_head`（从参考文章提取的 head 片段）本身已包含 `<!DOCTYPE html><html><head>`，导致最终输出 `<!DOCTYPE html>\n<!DOCTYPE html>` 双重 DOCTYPE。

**修复**：保存后检查并清理多余 DOCTYPE：
```python
html = html.replace('<!DOCTYPE html>', '', 1) if html.count('<!DOCTYPE html>') > 1 else html
```

#### 封面图下载必须在 og:image 替换之前

重下载脚本中，必须先保存原始 og:image 的 CDN URL 并下载封面，**然后**才能把 og:image 替换为 `cover.jpg`。一旦提前替换，原始 URL 就丢失了，无法下载正确封面。

```python
# ✅ 正确顺序
og_url = soup.find('meta', property='og:image')['content']  # 先保存
# ... 下载图片并保存为 cover.jpg ...
download_cover(og_url, 'cover.jpg')
# 然后替换
html = html.replace(og_url, 'cover.jpg')
```

#### share_content_page 模板的 H1 替换

`share_content_page` 类型文章的标题元素是 `<h1 class="rich_media_title no_desc_title">`，而非标准 `appmsg` 类型的 `<h1 id="activity-name">`。模板替换时必须同时处理两种格式，否则模板原标题会残留：

```python
# appmsg 类型
h1 = soup.find(id='activity-name')
nh = new_soup.find(id='activity-name')
if h1 and nh:
    nh.clear()
    sp = new_soup.new_tag('span')
    sp['class'] = 'js_title_inner'
    sp.string = h1.get_text(strip=True)
    nh.append(sp)

# share_content_page 类型（补充）
if not (h1 and nh):
    live_h1 = soup.find('h1')
    new_h1 = new_soup.find('h1')
    if live_h1 and new_h1:
        new_h1.string = live_h1.get_text(strip=True)
```

**已知污染案例**：`2025-03-24_2.7.5_根本放不下` 文章用 `小雪伊始` 模板替换后，因未替换 H1，页面显示「小雪伊始，一场清染人间的洁白，向天地万物问候冬安。」标题。

### 单篇文章重下载流程（改进版，download_single.py 已内置）

对于需要特殊处理的文章（如 `2025-03-24_2.7.5_根本放不下`），`download_single.py` 采用以下流程：

1. **网络拦截下载图片**：通过 Playwright `page.on('response')` 拦截 `mmbiz.qpic.cn` 等 CDN 响应，自然获取图片（带正确 Referer/Cookie）
2. **跳过 `_inline_css`**：不内联 WeChat CSS（会膨胀到 3MB+），由后处理脚本用模板 head 替换
3. **滚动触发懒加载**：分段 `scrollTo` 确保所有懒加载图片被激活
4. **兜底 aiohttp 下载**：未拦截到的图片用 aiohttp 补下

完整流水线（必须按顺序执行）：
```bash
# 1. 下载（更新 URL 后运行）
cd wechat-archive-tool && python download_single.py

# 2. 后处理（模板 head 替换 + 封面下载 + 元数据）
cd .. && python scripts/post_process.py "2025-03-24_2.7.5_根本放不下"

# 3. 修复 og:image（post_process.py 会留下远程 CDN URL，必须替换为本地 cover.jpg）
#    fix_og.py 脚本：替换 og:image 和 twitter:image 的 content 为 cover.jpg

# 4. 优化（CSS 去重 + 图片压缩 + HTML 压缩 + 元数据）
python scripts/optimize_wechat.py
```

**该文章特殊要点**：
- URL 使用短链接 `https://mp.weixin.qq.com/s/5tWwUJKCVuQYr2E_crKrkw`（长链接 `__biz=...` 容易触发 CAPTCHA）
- 文章类型：`appmsg`（标准文章），body class 为 `mm_appmsg`，图文混排，含 8 张图片 + 1 张封面
- 图片使用 `mmecoa.qpic.cn` CDN（非 `mmbiz.qpic.cn`），下载时需覆盖该域名
- `post_process.py` 会将其误判为 `share_content_page`（因为 WeChat 框架 CSS 含 `share_content_page_bd`），应手动用 appmsg 模板替换 head

### `_clean_html()` 维护记录

- `remove_ids` 中已添加 `wx_stream_article_slide_tip`（消除「继续滑动看下一个」）
- 移动端 grid 布局 CSS 选择器已限定为 `.share_content_page #js_article`，不再影响普通文章
- `download_single.py` 原版缺少 `_inline_css` 步骤，已补充

### 图片下载格式检测

- `_download_body_images()` 和 bg 图片下载中，URL 无明确扩展名时不再盲目默认 `.jpg`
- 改为依次检测：HTTP Content-Type → 文件魔数字节（`\x89PNG` / `GIF` / `\xff\xd8` 等）→ 兜底 `.jpg`
- 这解决了 WeChat CDN 透明 PNG 图标被存成 JPG 导致黑底的问题
- 位置：`src/downloader.py` 第 553-585 行（body images）和 610-632 行（bg images）

### 图片型文章（share_single_img / img_share）处理

- 此类文章（body class 含 `share_single_img`）的封面图由 `_expand_swiper_images` 正常提取，走标准下载流程即可
- **严禁**从 JSON 的 `cdn_url` 字段额外提取图片注入 —— 那些是缩略图/图标，会破坏页面结构
- **严禁**修改 `_expand_swiper_images` 去删除 `share_media_swiper_wrp` —— 它包含封面图引用，必须保留
- 标准下载流程：`_fix_image_urls` → `_inline_css` → `_clean_html` → `_download_body_images`
- 桌面视图下 `share_content_page_bd` 默认宽度 355px（WeChat CSS），标题栏偏窄
- **修复**：给 `share_content_page_bd` 元素添加 inline style `width:500px !important`，使用 inline style 确保优先级最高
- 也可用 CSS 注入：`@media(min-width:769px){.page_share_img .share_content_page_bd{width:500px !important}}`

### 文章后处理 (`scripts/post_process.py`)

- **用途**：下载完成后统一修复不同文章类型的 CSS/布局问题
- **用法**：`python scripts/post_process.py <目录名>`
- 自动检测文章类型（`share_content_page` / `appmsg`），用对应参考文章的 head CSS 替换
- share_content_page 类型额外修复：`share_content_page_bd` 宽度 → 500px
- 自动下载缺失的封面图（og:image）
- 自动更新 `wechat-metadata.json`
- **参考文章**：
  - `share_content_page` 类型 → `2024-11-26_小雪伊始`（桌面两栏 flex 布局）
  - `appmsg` 类型 → `2024-12-15_冬日畅言`（标准 WeChat 样式）

### SVG 占位符与模板区块处理

- WeChat 编辑器在正文中插入大量 `<svg viewbox="0 0 1 1">` 空占位符，用于装饰性图标容器
- 静态页下这些 SVG 无 JS 激活，渲染成暗色块（或其父 section 的 `background-color` 透出）
- CSS 修复已注入（`_clean_html()` 中）：
  - `svg[viewbox="0 0 1 1"]{display:none!important}` — 隐藏空 SVG
  - `section:has(>svg){background-color:transparent!important}` — 图标容器背景透明化
  - `.js_img_placeholder,.wx_img_placeholder{opacity:1!important}` — 懒加载占位图强制可见

### 移动端布局 CSS（`@media(max-width:768px)`）

- grid 双行布局：正文区 `minmax(160px,300px)` 在上，封面图 `auto` 在下
- 正文区内 flex 排序：标题(order:1) → meta/地区(order:2) → 简介(order:3)
- 左对齐：标题 `padding:12px 16px`，meta `padding:4px 16px`，简介 `padding:8px 16px`
- meta 嵌套结构（`meta_list` 包 `meta_area_extra`）已拆分为父子分离 padding，避免双层缩进

## 文章目录过滤

- 排除列表在 `doc/wechat.data.js` 和 `scripts/optimize_wechat.py` 的 SKIP 数组中
- 还自动排除标题以「转载」开头的文章
- 修改排除列表后需重新运行 `optimize_wechat.py` + `pnpm run build`

## 占位符 class 清理（静态页图片显示修复）

### 问题背景

WeChat 页面在 JS 激活前使用占位符 class 隐藏/遮蔽图片，静态页无 JS，因此图片不显示或显示加载圈。

### 需要移除的 class

1. **`js_img_placeholder` / `wx_img_placeholder`** — 图片标签上的懒加载占位符 class
   - 存在于 `<img class="rich_pages wxw-img js_img_placeholder wx_img_placeholder">` 中
   - 移除后图片正常显示透明背景，不再有加载圈圈
   - 注意：这两个 class 可能在 `class` 属性开头（`class="js_img_placeholder"`），正则替换时不要依赖前导空格

2. **`wx_imgbc_placeholder`** — 背景图容器的懒加载占位 class
   - 存在于 `<section class="wx_imgbc_placeholder">` 中
   - 配合 `data-lazy-bgimg` 使用

### `data-lazy-bgimg` 背景图懒加载

WeChat 的背景图懒加载机制：元素通过 `data-lazy-bgimg="真实图片名"` 引用实际图片，但内联 `style` 中的 `background-image` 被替换为 1x1 透明 GIF 的 base64 占位符。JS 激活后才替换为真实图片。

**修复方法**：将 `background-image: url("data:image/gif;base64,...")` 替换为 `background-image: url("真实图片名")`（从 `data-lazy-bgimg` 取值）。

### 批处理脚本

2025-05 对 2023 年及以前所有文章（863 篇）执行了批量修复，处理了以下问题：

1. **远程 CDN 图片下载**（316/549 成功，233 失败）
   - 成功：通过 Playwright `page.evaluate()` → `fetch()` 下载并替换为本地文件
   - 失败：大部分是 CDN 已过期的装饰性细条占位图（256×15 等，CDN 返回 404/403），或需要特定 Cookie 的图片
   - 下载时用魔数字节检测实际格式（`\x89PNG`/`GIF`/`\xff\xd8`/`RIFF`），避免扩展名误判

2. **data-lazy-bgimg → background-image 替换**（1,489 个元素）
   - 将 `background-image: url("data:image/gif;base64,...")` 替换为 `background-image: url("本地文件名")`
   - 注意：替换后 `data-lazy-bgimg` 属性仍保留在元素上（无害），不需要删除

3. **占位符 class 清理**（244 个图片/容器）
   - 移除 `js_img_placeholder`、`wx_img_placeholder`、`wx_imgbc_placeholder`

4. **图片格式纠正**
   - 扫描所有 img_* 文件，魔数字节检测实际格式，扩展名不匹配则重命名并更新 HTML 引用
   - 本次扫描发现 863 篇文章中无格式错误（之前已修复）

5. **视频下载**
   - 查找 `<mp-common-videosnap>` 标签，尝试下载 `data-url` 中的视频

脚本位置：`wechat-archive-tool/batch_fix.py`

## 微信 CDN 防盗链与图片下载

### 问题根因

WeChat CDN（`mmbiz.qpic.cn`）对图片请求检查 Referer 和 Cookie。静态页从 `localhost` 访问时，Referer 不是 `mp.weixin.qq.com`，CDN 拒绝请求并返回"未经允许禁止使用"的提示图。

### 下载方式对比

| 方式 | 结果 | 原因 |
|------|------|------|
| `aiohttp` 直接请求 | 大量屏蔽 | 缺少 Referer + WeChat Cookie |
| Playwright `page.evaluate()` 调用 `fetch()` | 部分成功 | 在微信页面内 fetch，有 Referer 和 Cookie，但部分图片仍失败 |
| **Playwright 网络拦截**（`page.on('response')`） | **最佳** | 浏览器自然加载页面时发起请求，带有完整请求上下文（Referer、Cookie、微信特有头），CDN 放行 |

### 正确下载流程

1. Playwright 打开文章 URL（`wait_until='networkidle'`）
2. 注册 `page.on('response', handler)` 拦截所有图片响应
3. 滚动页面触发所有懒加载图片（`window.scrollTo` 分段滚动）
4. 收集所有 `mmbiz.qpic.cn` 的响应 body
5. 建立 CDN URL → 本地文件映射
6. 更新 HTML 中所有引用（`src`、`background-image`、`data-lazy-bgimg`）
7. **必须用模板文章的 head 重建 HTML**（避免 `_inline_css` 导致的样式膨胀），只替换 body 内容

### 容易被遗漏的远程 URL

除了 `<img src>`，以下位置也可能有 CDN URL：
- `style` 属性中的 `background-image: url("https://mmbiz.qpic.cn/...")`
- `data-lazy-bgimg` 属性
- `data-src` 属性（懒加载的原始图片 URL）

### URL 清理

下载完成后需要清理：
- `#imgIndex=N` 片段（WeChat 图片索引标记，会导致本地文件匹配失败）
- `&amp;` → `&`（HTML 实体还原）

### 图片 CDN 域名不止 mmbiz

WeChat 文章中的图片可能使用多个 CDN 域名，不仅限于 `mmbiz.qpic.cn`：
- `mmbiz.qpic.cn` — 正文图片（最常见）
- `mmecoa.qpic.cn` — 封面图和部分图片（share_content_page 类文章常见）
- `mpcdn`、`res.wx.qq.com` — 装饰性资源

下载脚本中的 CDN URL 检测、网络拦截、URL 替换、远端引用验证都必须覆盖所有这些域名：

```python
# ❌ 只检查 mmbiz.qpic.cn
if 'mmbiz.qpic.cn' in url:
    ...

# ✅ 检查所有 WeChat CDN 域名
def is_cdn(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mmecoa.qpic.cn', 'mpcdn', 'res.wx.qq.com'])
```

## 文章重下载后样式丢失

### 问题

用 `download_single.py` 或自定义脚本重新下载文章后，HTML 体积暴涨（从 40KB 到 800KB），页面样式混乱。

### 原因

下载器调用 `_inline_css()` 把全部 WeChat UI 框架 CSS（43 个 style 标签）内联到 HTML 中。正常流程中 `optimize_wechat.py` 会把这些内联 CSS 提取为共享文件并替换成 `<link>` 标签，但单篇重下载后没有运行优化。

### 解决

取一篇正常文章的 HTML 结构作为模板（含共享 CSS 的 `<link>` 标签），只把重新下载的文章的 body 内容（`#js_content` 内部）替换进去。同时替换元数据（title、og:title、author、publish_time 等）。

### 注意事项

- 替换 body 内容后必须同时更新 `#activity-name`（h1 标题）、`#js_author_name_text`、`#publish_time`、`#js_name` 等元素
- BeautifulSoup 的 `append()` 是移动操作（非复制），会导致源元素被掏空。如需保留源结构，先用 `copy()` 或手动重建。
- 如果 H1 标题丢失，从 `<meta property="og:title">` 读取并写入 `<span class="js_title_inner">`

## 文本替换

下载的 HTML 中「大冲在思考」需全局替换为「沈理电协」（`download_single.py` 第 100 行有此逻辑，但自定义重下载脚本容易遗漏）。

## 图片文件格式误判

CDN URL 中 `wx_fmt` 参数与实际响应 Content-Type 可能不一致。保存图片时应优先检测文件魔数字节（`\x89PNG`、`GIF`、`\xff\xd8`、`RIFF`），而非仅依赖 URL 扩展名。SVG 文件可能被误判为 JPG（357B 的 SVG 图标会被存为 .jpg），需额外检测 `<?xml` 或 `<svg` 标签。

## 硬性规则

- **不得有任何远程引用**：最终 HTML 中不允许出现任何 `https://mmbiz.qpic.cn` 或 `https://mp.weixin.qq.com` 的 URL 引用（包括 `src`、`background-image`、`data-lazy-bgimg`、`og:image`、`og:url` 等属性）。所有图片必须下载到本地目录，所有链接必须使用相对路径。
- **下载完成后必须验证远程引用**：用 `grep` 或正则检查最终 HTML 中是否还有 `mmbiz.qpic.cn` 或 `mp.weixin.qq.com/s/`，确保为 0。
- **og:url 保留原始微信链接**：虽然最终页面不引用远程资源，但 `og:url` 应保留原始 `https://mp.weixin.qq.com/s/...` 链接作为元数据，不要替换。
- **og:image 必须指向本地文件**：封面图的 `og:image` 和 `twitter:image` 应指向本地 `cover.jpg`，不能是远程 CDN URL。

## 模板替换陷阱

### js_content 空值污染

用模板重建 HTML 时，**必须先检查直播页的 `#js_content` 是否有内容**。如果直播页加载失败（CAPTCHA、网络错误等），`js_content` 为空或不存在，此时直接替换 body 内容会导致原文章被模板的"加油考研人"等内容覆盖，造成不可逆的内容丢失。

```python
# 正确做法
js = live_soup.find(id='js_content')
if not js or len(js.get_text(strip=True)) < 50:
    print('WARNING: live page has no js_content, skipping to avoid corruption')
    return False
```

### BeautifulSoup `&` 转义

BeautifulSoup 的 `str(soup)` 或 `.write_text()` 会将 URL 中的 `&` 转义为 `&amp;`。嵌入 iframe 等需要精确 URL 的场景，必须在保存后用字符串替换还原：
```python
result = result.replace('&amp;', '&')
```

### 文件名参数污染

URL 替换时容易把查询参数也拼到文件名里（如 `rem_2.png&tp=webp&wxfrom=5`），导致文件找不到。替换后需清理：
```python
html = re.sub(r'(img_\d+\.\w+)&[^"]+', r'\1', html)
html = re.sub(r'(rem_\d+\.\w+)&[^"]+', r'\1', html)
```

## 视频替换

微信文章中的视频在静态页显示为 `<span class="video_iframe rich_pages">` 占位符。替换为 Bilibili 等嵌入式播放器时：

1. 创建 `<iframe>` 指向播放器 URL（注意用 `https:` 完整 URL，非 `//` 协议相对）
2. 删除 `<span class="video_iframe">` 及其父级空壳 `<section>`
3. 添加 `autoplay=0` 参数禁止自动播放

## 微信 CAPTCHA 与频率限制

- 短时间内大量请求会触发"操作过于频繁"限流，后续请求被 CAPTCHA 拦截
- 被限流后需等待冷却（约 30 分钟）
- 可通过 Playwright `headless=False` 打开浏览器让用户手动完成验证
- 验证通过后保存 Cookies 供后续请求使用
- **CAPTCHA 针对浏览器指纹，非 IP**：本机普通浏览器能访问但 Playwright 被拦，说明检测的是自动化特征
- **反检测方案**：
  1. 安装 `playwright-stealth`：`pip install playwright-stealth`
  2. 使用 `Stealth` + `apply_stealth_async(page)` 隐藏 webdriver 标记
  3. 设置真实 User-Agent 和 viewport
  4. 增加请求间隔（5s+）
  5. 长链接（`s?__biz=...`）更容易触发验证，优先用短链接（`s/xxxxx`）

## 已知问题

- `no_desc_title` 类文章（图片分享型）在手机端标题可能不可见，可删目录重下
- VitePress 中 `.md` 文件不要用 `<template>` 标签，用 `<div>` 代替
- `_clean_html` 中 `_expand_swiper_images` 必须在所有 dom 删除之前调用
- 微信 CDN 对部分旧文章图片返回 256x15 或 580x20 的装饰性细条占位符（文件大小 14KB 左右），这是 CDN 服务端限制，浏览器也无法绕过
- `download_single.py` 的 `_inline_css` 后需要运行 `optimize_wechat.py` 做 CSS 去重，否则样式炸裂
- 批量重下载脚本会覆盖手动修改（如视频嵌入），处理顺序需注意

## 常用命令

```bash
# 开发
pnpm dev                          # VitePress 开发服务器

# 下载文章（本地运行，需要浏览器扫码登录）
cd wechat-archive-tool && python main.py

# 构建部署
python3 scripts/optimize_wechat.py  # 优化图片/CSS
pnpm run build                      # 构建 VitePress
```

## 操作原则

- **重启 dev server、pnpm 命令等由用户自己操作**，不要代为执行。AI 只负责文件修改和脚本运行。
- **严禁批量删除文章目录**：只处理指定文章，不要通配删除同日期其他文章。即使修复脚本也只在确认后再操作，不得自动 `shutil.rmtree` 删除目录。
