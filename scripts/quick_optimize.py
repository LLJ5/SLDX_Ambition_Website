"""
Run optimizer steps 1 (CSS dedup), 5 (HTML minify), 6 (metadata) - skip slow network steps
"""
import re, hashlib, json
from pathlib import Path
from collections import defaultdict

PROJ = Path(__file__).resolve().parent.parent
ARTICLES = PROJ / 'doc/public/wechat/articles'
SHARED = ARTICLES / '_shared'
METADATA_JSON = PROJ / 'doc/public/wechat/wechat-metadata.json'
MIN_COVERAGE = 0.8

html_files = sorted(ARTICLES.glob('*/index.html'))
print(f'Found {len(html_files)} HTML files')

# Step 1: CSS Dedup
print('[1/3] CSS Deduplication')
block_counts = defaultdict(int)
block_sample = {}
for fp in html_files:
    html = fp.read_text(encoding='utf-8')
    blocks = re.findall(r'<style[^>]*>.*?</style>', html, re.DOTALL)
    seen = set()
    for b in blocks:
        h = hashlib.md5(b.encode()).hexdigest()
        if h not in seen:
            block_counts[h] += 1
            block_sample[h] = b
            seen.add(h)

threshold = max(1, int(len(html_files) * MIN_COVERAGE))
common = sorted(
    [(h, cnt, block_sample[h]) for h, cnt in block_counts.items() if cnt >= threshold],
    key=lambda x: -len(x[2])
)
print(f'  Found {len(common)} common CSS blocks (>={threshold}/{len(html_files)} files)')

SHARED.mkdir(parents=True, exist_ok=True)
css_map = {}
block_content = {}
for idx, (h, cnt, block) in enumerate(common):
    inner = re.sub(r'</?style[^>]*>', '', block).strip()
    fname = f's{idx:03d}.css'
    (SHARED / fname).write_text(inner, encoding='utf-8')
    css_map[h] = fname
    block_content[h] = block
    print(f'    {fname}: {len(inner):,} bytes ({cnt} files)')

# Rewrite HTML
saved = 0
for i, fp in enumerate(html_files):
    html = fp.read_text(encoding='utf-8')
    orig = len(html)
    for h in css_map:
        if block_content[h] in html:
            html = html.replace(block_content[h], f'<link rel="stylesheet" href="../_shared/{css_map[h]}">')
    if orig != len(html):
        fp.write_text(html, encoding='utf-8')
        saved += orig - len(html)
    if (i + 1) % 200 == 0:
        print(f'    Rewrite {i+1}/{len(html_files)}...')
print(f'  Saved {saved / 1e6:.1f} MB')

# Step 5: HTML Minification
print('[2/3] HTML Minification')
saved = 0
for fp in html_files:
    html = fp.read_text(encoding='utf-8')
    orig = len(html)
    parts = re.split(r'(<pre[^>]*>.*?</pre>|<code[^>]*>.*?</code>)', html, flags=re.DOTALL)
    result = []
    for part in parts:
        if part.startswith('<pre') or part.startswith('<code'):
            result.append(part)
        else:
            part = re.sub(r'\n\s*\n', '\n', part)
            part = re.sub(r'>\s+<', '><', part)
            result.append(part)
    html = ''.join(result)
    fp.write_text(html, encoding='utf-8')
    saved += orig - len(html)
print(f'  Saved {saved / 1e6:.1f} MB')

# Step 6: Metadata
print('[3/3] Metadata Generation')
SKIP = ['2026-05-22_公众号运营回归个人通知', '2025-09-15_我们搬家啦',
        '2025-06-03_沈理电协Ambition战队官网发布', '2025-06-18_大疆_2026_校招',
        '2024-06-13_大疆_2025', '2024-07-04_DJI_大疆',
        '2024-07-07_测一测你来_DJI', '2022-04-25_下一场，去大疆',
        '2018-04-13_DJI大疆创新RoboMaster机器人夏令营', '2018-03-09_RoboMaster2018最全招聘',
        '2025-03-06_机甲大师十周年徽章，即将发布', '2015-10-01_沈阳周边竟隐藏了十个小众旅游天堂！美得窒息！十一走起！']

articles = []
for entry_dir in sorted(ARTICLES.iterdir()):
    if not entry_dir.is_dir() or entry_dir.name.startswith('_'):
        continue
    if any(entry_dir.name.startswith(s) for s in SKIP):
        continue
    title_part = entry_dir.name[11:]
    if title_part.startswith('转载') or title_part.startswith('转载_'):
        continue
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_(.*)', entry_dir.name)
    if not m:
        continue
    date_str, _ = m.groups()
    html_path = entry_dir / 'index.html'
    title = entry_dir.name[11:].replace('_', ' ')
    content = ''
    if html_path.exists():
        content = html_path.read_text(encoding='utf-8')
        tm = re.search(r'<title>(.*?)</title>', content)
        if tm:
            import html as h
            title = h.unescape(tm.group(1).strip())
        title = title.replace('&amp;', '&')
    has_cover = False
    cover_ext = None
    for ext in ('jpg', 'png', 'webp'):
        if (entry_dir / f'cover.{ext}').exists():
            has_cover = True
            cover_ext = ext
            break
    has_video = bool(re.search(r'<video\b|<mpvideo\b|video_\w+\.mp4|v\.qq\.com|bilibili\.com/player', content)) if content else False
    articles.append({
        'date': date_str, 'year': int(date_str[:4]),
        'title': title, 'dir': entry_dir.name,
        'hasCover': has_cover, 'coverExt': cover_ext,
        'hasVideo': has_video
    })

articles.sort(key=lambda a: a['date'], reverse=True)
METADATA_JSON.write_text(json.dumps(articles, ensure_ascii=False), encoding='utf-8')
print(f'  {len(articles)} articles')

total = sum(f.stat().st_size for f in ARTICLES.rglob('*') if f.is_file())
print(f'\nTotal: {total / 1e6:.1f} MB')
print('Done - refresh the page')
