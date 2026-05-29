
"""
文章后处理脚本：自动检测文章类型并应用对应修复
用法：python scripts/post_process.py <article_directory_name>
"""
import re, sys, json, urllib.request
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
ARTICLES = PROJ / 'doc/public/wechat/articles'
METADATA = ARTICLES.parent / 'wechat-metadata.json'

# ─── 参考文章（选项目中已知正常的代表） ───
REF_DIRS = {
    'share_content_page': '2024-11-26_小雪伊始，一场清染人间的洁白，向天地万物问候冬安。',
    'appmsg':            '2024-12-15_冬日畅言___RM线下交流会',
}

def get_meta(html, pattern):
    m = re.search(pattern, html)
    return m.group(1) if m else ''

def detect_type(html):
    """检测文章类型"""
    if 'share_content_page' in html and 'share_content_page_bd' in html:
        return 'share_content_page'
    if 'rich_media' in html and 'rich_media_content' in html:
        return 'appmsg'
    return 'unknown'

def fix_share_content_page(html, ref_head):
    """修复图片分享型文章"""
    body_start = html.find('<body')
    head = html[:body_start]
    body = html[body_start:]
    meta_end = body.find('>') + 1 if body.startswith('<body') else 0
    body_tag = body[:meta_end]
    body_content = body[meta_end:]
    
    # 1. bd 宽度修复
    body_content = body_content.replace(
        'class="share_content_page_bd" id="js_base_container"',
        'class="share_content_page_bd" id="js_base_container" style="width:500px !important"'
    )
    
    # 2. 替换 head 为参考文章 head（保留 meta）
    new_head = ref_head
    meta_map = {
        'TITLE':         ('<title>(.*?)</title>',                              lambda m: m.group(1)),
        'OG_TITLE':      ('property="og:title"\\s+content="([^"]*)"',         lambda m: m.group(1)),
        'OG_URL':        ('property="og:url"\\s+content="([^"]*)"',           lambda m: m.group(1)),
        'OG_IMAGE':      ('property="og:image"\\s+content="([^"]*)"',         lambda m: m.group(1)),
        'TWITTER_IMAGE': ('name="twitter:image"\\s+content="([^"]*)"',        lambda m: m.group(1)),
        'DESC':          ('name="description"\\s+content="([^"]*)"',          lambda m: m.group(1)),
        'OG_DESC':       ('property="og:description"\\s+content="([^"]*)"',   lambda m: m.group(1)),
        'TWITTER_DESC':  ('name="twitter:description"\\s+content="([^"]*)"',  lambda m: m.group(1)),
        'AUTHOR':        ('name="author"\\s+content="([^"]*)"',               lambda m: m.group(1)),
        'OG_AUTHOR':     ('property="og:article:author"\\s+content="([^"]*)"',lambda m: m.group(1)),
        'TWITTER_TITLE': ('name="twitter:title"\\s+content="([^"]*)"',        lambda m: m.group(1)),
        'TWITTER_CREATOR':('name="twitter:creator"\\s+content="([^"]*)"',     lambda m: m.group(1)),
    }
    
    for key, (pattern, _) in meta_map.items():
        old_m = re.search(pattern, head)
        new_m = re.search(pattern, new_head)
        if old_m and new_m and old_m.group(1) != new_m.group(1):
            new_head = new_head.replace(new_m.group(1), old_m.group(1))
    
    # 特殊处理 title 标签
    old_title = re.search(r'<title>(.*?)</title>', head)
    new_title = re.search(r'<title>(.*?)</title>', new_head)
    if old_title and new_title and old_title.group(1) != new_title.group(1):
        new_head = new_head.replace(new_title.group(0), old_title.group(0))
    
    return '<!DOCTYPE html>\n' + new_head + '</head>\n' + body_tag + body_content

def fix_appmsg(html, ref_head):
    """修复普通文章"""
    body_start = html.find('<body')
    head = html[:body_start]
    body = html[body_start:]
    meta_end = body.find('>') + 1 if body.startswith('<body') else 0
    body_tag = body[:meta_end]
    body_content = body[meta_end:]
    
    new_head = ref_head
    
    # 替换 meta
    meta_map = {
        'TITLE':         ('<title>(.*?)</title>',                              lambda m: m.group(1)),
        'OG_TITLE':      ('property="og:title"\\s+content="([^"]*)"',         lambda m: m.group(1)),
        'OG_URL':        ('property="og:url"\\s+content="([^"]*)"',           lambda m: m.group(1)),
        'OG_IMAGE':      ('property="og:image"\\s+content="([^"]*)"',         lambda m: m.group(1)),
        'TWITTER_IMAGE': ('name="twitter:image"\\s+content="([^"]*)"',        lambda m: m.group(1)),
        'DESC':          ('name="description"\\s+content="([^"]*)"',          lambda m: m.group(1)),
        'OG_DESC':       ('property="og:description"\\s+content="([^"]*)"',   lambda m: m.group(1)),
        'TWITTER_DESC':  ('name="twitter:description"\\s+content="([^"]*)"',  lambda m: m.group(1)),
        'AUTHOR':        ('name="author"\\s+content="([^"]*)"',               lambda m: m.group(1)),
        'OG_AUTHOR':     ('property="og:article:author"\\s+content="([^"]*)"',lambda m: m.group(1)),
        'TWITTER_TITLE': ('name="twitter:title"\\s+content="([^"]*)"',        lambda m: m.group(1)),
        'TWITTER_CREATOR':('name="twitter:creator"\\s+content="([^"]*)"',     lambda m: m.group(1)),
    }
    
    for key, (pattern, _) in meta_map.items():
        old_m = re.search(pattern, head)
        new_m = re.search(pattern, new_head)
        if old_m and new_m and old_m.group(1) != new_m.group(1):
            new_head = new_head.replace(new_m.group(1), old_m.group(1))
    
    old_title = re.search(r'<title>(.*?)</title>', head)
    new_title = re.search(r'<title>(.*?)</title>', new_head)
    if old_title and new_title and old_title.group(1) != new_title.group(1):
        new_head = new_head.replace(new_title.group(0), old_title.group(0))
    
    return '<!DOCTYPE html>\n' + new_head + '</head>\n' + body_tag + body_content

def download_cover(article_dir, html):
    """下载封面图"""
    for ext in ('jpg', 'png', 'webp', 'gif'):
        if (article_dir / f'cover.{ext}').exists():
            return True
    
    m = re.search(r'content="(http[^"]*mmbiz\.qpic\.cn[^"]*)"', html)
    if not m:
        m = re.search(r'content="(http[^"]*mmecoa\.qpic\.cn[^"]*)"', html)
    if not m:
        return False
    
    url = m.group(1)
    ext = 'jpg'
    for fmt in ('png', 'gif', 'webp'):
        if f'wx_fmt={fmt}' in url:
            ext = fmt
            break
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://mp.weixin.qq.com/',
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            (article_dir / f'cover.{ext}').write_bytes(resp.read())
        print(f'  Cover downloaded: cover.{ext}')
        return True
    except Exception as e:
        print(f'  Cover failed: {e}')
        return False

def update_metadata():
    """更新元数据 JSON"""
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
            if tm: title = tm.group(1).strip()
            title = title.replace('&amp;', '&')
        has_cover = False
        cover_ext = None
        for ext in ('jpg', 'png', 'webp', 'gif'):
            if (entry_dir / f'cover.{ext}').exists():
                has_cover = True; cover_ext = ext; break
        has_video = bool(re.search(r'<video\b|<mpvideo\b|video_\w+\.mp4|v\.qq\.com|bilibili', content)) if content else False
        articles.append({
            'date': date_str, 'year': int(date_str[:4]),
            'title': title, 'dir': entry_dir.name,
            'hasCover': has_cover, 'coverExt': cover_ext,
            'hasVideo': has_video
        })
    articles.sort(key=lambda a: a['date'], reverse=True)
    METADATA.write_text(json.dumps(articles, ensure_ascii=False), encoding='utf-8')
    print(f'  Metadata: {len(articles)} articles')

def process_article(dir_name):
    """处理单篇文章"""
    article_dir = ARTICLES / dir_name
    if not article_dir.is_dir():
        # Try glob match
        matches = list(ARTICLES.glob(dir_name + '*'))
        if not matches:
            print(f'ERROR: Article dir not found: {dir_name}')
            return
        article_dir = matches[0]
    
    html_path = article_dir / 'index.html'
    if not html_path.exists():
        print(f'ERROR: No index.html in {article_dir.name}')
        return
    
    html = html_path.read_text(encoding='utf-8')
    article_type = detect_type(html)
    print(f'Processing: {article_dir.name}')
    print(f'  Type: {article_type}')
    
    if article_type == 'unknown':
        print('  Unknown type, skipping')
        return
    
    # 加载参考 head
    ref_name = REF_DIRS.get(article_type)
    ref_dir = next(ARTICLES.glob(ref_name[:12] + '*'))
    ref_html = (ref_dir / 'index.html').read_text(encoding='utf-8')
    ref_head = ref_html[:ref_html.find('</head>')]
    
    if article_type == 'share_content_page':
        new_html = fix_share_content_page(html, ref_head)
    else:
        new_html = fix_appmsg(html, ref_head)
    
    html_path.write_text(new_html, encoding='utf-8')
    
    # 下载封面
    download_cover(article_dir, new_html)
    
    # 更新元数据
    update_metadata()
    print(f'  Done: {article_dir.name}\n')

# ─── CLI ───
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/post_process.py <article_dir_name>')
        print('  article_dir_name: exact dir name or prefix match')
        sys.exit(1)
    
    process_article(sys.argv[1])
