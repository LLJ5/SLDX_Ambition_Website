"""Simple Tool: Download WeChat article from cloud and replace local file."""
import asyncio, json, re, os, sys
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import quote

BASE = Path(os.path.dirname(os.path.abspath(__file__))).parent / 'doc' / 'public' / 'wechat' / 'articles'
COOKIES = Path(__file__).parent / 'wechat_cookies.json'

def detect_ext(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:6] in (b'GIF89a', b'GIF87a'): return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    return 'jpg'

def is_cdn(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mmecoa.qpic.cn', 'mpcdn', 'res.wx.qq.com'])

def list_articles():
    """List all article directories."""
    dirs = []
    for d in sorted(BASE.iterdir(), reverse=True):
        if not d.is_dir() or d.name.startswith('_'):
            continue
        m = re.match(r'^(\d{4}-\d{2}-\d{2})_', d.name)
        if not m:
            continue
        html_path = d / 'index.html'
        title = d.name[11:].replace('_', ' ')[:60]
        if html_path.exists():
            try:
                m2 = re.search(r'<title>([^<]+)</title>', html_path.read_text('utf-8')[:5000])
                if m2: title = m2.group(1).strip()
            except: pass
        dirs.append((d.name, m.group(1), title))
    return dirs

def find_dir_by_url(wechat_url):
    """Find article directory by matching og:url in index.html."""
    search_key = wechat_url.split('/s/')[1].split('?')[0].split('#')[0] if '/s/' in wechat_url else ''
    if not search_key:
        search_key = wechat_url.split('sn=')[1].split('&')[0] if 'sn=' in wechat_url else ''
    if not search_key:
        return None
    
    for d in BASE.iterdir():
        if not d.is_dir() or d.name.startswith('_'):
            continue
        html_path = d / 'index.html'
        if not html_path.exists():
            continue
        try:
            html = html_path.read_text('utf-8')[:10000]
            if search_key[:10] in html:
                return d
        except:
            continue
    return None

def search_articles(keyword):
    """Search article directories by keyword."""
    all_dirs = list_articles()
    if not keyword:
        return all_dirs[:50]
    kw = keyword.lower()
    return [(n, d, t) for n, d, t in all_dirs if kw in n.lower() or kw in t.lower()][:50]

async def download_and_replace(wechat_url, article_dir_name, article_type, throttle_kbps=0):
    """Download article from WeChat and replace local file."""
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    article_dir = BASE / article_dir_name
    if not article_dir.exists():
        return False, f"Directory not found: {article_dir_name}"

    # Load templates
    templates = {}
    for d in BASE.iterdir():
        if d.is_dir() and '冬日畅言' in d.name:
            templates['appmsg'] = (d / 'index.html').read_text('utf-8')
        if d.is_dir() and '小雪伊始' in d.name:
            templates['share_content_page'] = (d / 'index.html').read_text('utf-8')

    template_html = templates.get(article_type)
    if not template_html:
        return False, f"Template not found for type: {article_type}"

    logs = []

    import random as _random

    _UA_POOL = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    ]
    _VW = _random.randint(1024, 1920)
    _VH = _random.randint(768, 1080)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel='chrome', headless=True)
        except:
            browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=_random.choice(_UA_POOL),
            viewport={'width': _VW, 'height': _VH}
        )
        if COOKIES.exists():
            try: await ctx.add_cookies(json.loads(COOKIES.read_text()))
            except: pass

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        if throttle_kbps > 0:
            cdp = await ctx.new_cdp_session(page)
            await cdp.send('Network.emulateNetworkConditions', {
                'offline': False,
                'downloadThroughput': throttle_kbps * 1024 // 8,
                'uploadThroughput': throttle_kbps * 1024 // 8,
                'latency': 50
            })
            logs.append(f"Bandwidth throttled to {throttle_kbps} KB/s")

        # Network interception
        captured = {}
        async def hdl(response):
            url = response.url
            if response.status == 200 and is_cdn(url):
                try:
                    body = await response.body()
                    if body and len(body) > 200:
                        captured[url] = body
                        captured[url.split('?')[0]] = body
                except: pass
        page.on('response', hdl)

        logs.append(f"Opening: {wechat_url[:80]}...")
        try:
            await page.goto(wechat_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)
            # Scroll to trigger all lazy images — use dynamic page height
            total_h = await page.evaluate('document.body.scrollHeight')
            step = 300
            for pos in range(0, total_h + step, step):
                await page.evaluate(f'window.scrollTo(0, {pos})')
                await asyncio.sleep(0.15)
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(2)
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(1)
            html = await page.content()
        except Exception as e:
            await browser.close()
            return False, f"Failed to load page: {e}"

        soup = BeautifulSoup(html, 'lxml')
        js = soup.find(id='js_content')

        if not js or len(str(js)) < 2000:
            await browser.close()
            return False, "Page has no content (empty js_content)"

        logs.append(f"Content: {len(str(js))} chars, {len(js.find_all('img'))} imgs, {len(captured)} images captured")

        # Save og:image URL FIRST
        og_img = soup.find('meta', property='og:image')
        og_img_url = og_img['content'] if og_img and og_img.get('content') else None
        logs.append(f"Cover URL: {og_img_url[:80] if og_img_url else 'N/A'}")

        # Collect CDN URLs — normalize all to https:// (fetch() blocks http:// mixed content)
        all_urls = set()
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and is_cdn(val):
                    val = ('https:' + val) if val.startswith('//') else val
                    val = val.replace('http://', 'https://') if val.startswith('http://') else val
                    all_urls.add(val)

        for tag in js.find_all(style=True):
            st = tag.get('style', '')
            for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
                if is_cdn(m.group(1)):
                    u = m.group(1).replace('&amp;', '&')
                    u = u.replace('http://', 'https://') if u.startswith('http://') else u
                    all_urls.add(u)

        for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
            u = tag.get('data-lazy-bgimg', '')
            if is_cdn(u):
                u = ('https:' + u) if u.startswith('//') else u
                u = u.replace('http://', 'https://') if u.startswith('http://') else u
                all_urls.add(u)

        logs.append(f"CDN URLs found: {len(all_urls)}")

        # Delete old images
        for f in article_dir.glob('img_*'): f.unlink()
        for f in article_dir.glob('rem_*'): f.unlink()

        # Save images - normalize captured keys for fuzzy matching
        captured_normalized = {}
        for k, v in captured.items():
            base = k.split('?')[0].split('#')[0]
            captured_normalized[base] = v
            # Also store both protocol variants
            if base.startswith('http://'):
                captured_normalized[base.replace('http://', 'https://')] = v
            elif base.startswith('https://'):
                captured_normalized[base.replace('https://', 'http://')] = v
        
        url_map = {}
        for url in sorted(all_urls):
            base = url.split('?')[0].split('#')[0]
            data = captured_normalized.get(base)
            # Also try original lookup
            if not data:
                data = captured.get(url) or captured.get(url.split('?')[0])
            if not data:
                try:
                    result = await page.evaluate("""async (url) => {
                        try { const r = await fetch(url);
                        if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                        } catch(e) { return null; }
                    }""", url)
                    if result and len(result) > 200:
                        data = bytes(result)
                except: pass

            if data and len(data) > 200:
                ext = detect_ext(data)
                local = f'img_{len(url_map)+1}.{ext}'
                (article_dir / local).write_bytes(data)
                url_map[url] = local

        logs.append(f"Downloaded {len(url_map)} images")

        # Normalize url_map keys for better matching
        normalized_map = {}
        for cdn, loc in url_map.items():
            # Strip query and fragment, normalize http/https
            base = cdn.split('?')[0].split('#')[0]
            normalized_map[base] = loc
            # Also store with https
            if base.startswith('http://'):
                normalized_map[base.replace('http://', 'https://')] = loc
            elif base.startswith('https://'):
                normalized_map[base.replace('https://', 'http://')] = loc

        def match_url(html_url):
            """Find matching local filename for a CDN URL in HTML."""
            # Normalize: strip params, fragment
            base = html_url.split('?')[0].split('#')[0]
            if base in normalized_map:
                return normalized_map[base]
            # Try without protocol
            if base.startswith('https://'):
                base2 = base[8:]
                if base2 in normalized_map:
                    return normalized_map[base2]
            if base.startswith('http://'):
                base2 = base[7:]
                if base2 in normalized_map:
                    return normalized_map[base2]
            return None

        # Replace URLs in js_content
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and is_cdn(val):
                    val = ('https:' + val) if val.startswith('//') else val
                    loc = match_url(val)
                    if loc:
                        img[attr] = loc
            st = img.get('style', '')
            if st:
                for cdn, loc in url_map.items():
                    if cdn in st: st = st.replace(cdn, loc)
                img['style'] = st

        for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
            bg = tag.get('data-lazy-bgimg', '')
            if bg:
                loc = match_url(bg)
                if loc:
                    tag['data-lazy-bgimg'] = loc

        # Also replace in style attributes and content_bg
        for tag in js.find_all(style=True):
            st = tag.get('style', '')
            changed = False
            for m in re.finditer(r'url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
                url = m.group(1)
                loc = match_url(url)
                if loc:
                    st = st.replace(url, loc)
                    changed = True
            if changed:
                tag['style'] = st

        # Build new HTML with template
        new_soup = BeautifulSoup(template_html, 'lxml')

        # Copy metadata from live page
        for meta_name, attr in [('og:title','property'),('og:url','property'),
                                 ('og:description','property'),('og:site_name','property'),
                                 ('og:type','property'),('og:article:author','property'),
                                 ('twitter:title','property'),('twitter:site','property'),
                                 ('twitter:creator','property'),('twitter:description','property'),
                                 ('twitter:card','property'),('description','name'),('author','name')]:
            src = soup.find('meta', attrs={attr: meta_name})
            dst = new_soup.find('meta', attrs={attr: meta_name})
            if src and dst and src.get('content'):
                dst['content'] = src['content']

        # Title
        ti = new_soup.find('title')
        og_ti = soup.find('meta', property='og:title')
        if ti and og_ti and og_ti.get('content'):
            ti.string = og_ti['content']

        # js_content
        nj = new_soup.find(id='js_content')
        if nj:
            nj.clear()
            for c in list(js.contents):
                try: nj.append(c)
                except:
                    cc = BeautifulSoup(str(c), 'lxml').find()
                    if cc: nj.append(cc)

        # H1 title
        h1 = soup.find(id='activity-name')
        nh = new_soup.find(id='activity-name')
        if h1 and nh:
            nh.clear()
            sp = new_soup.new_tag('span')
            sp['class'] = 'js_title_inner'
            sp.string = h1.get_text(strip=True) or (og_ti['content'] if og_ti else '')
            nh.append(sp)
        # Fallback for share_content_page
        if not (h1 and nh):
            live_h1 = soup.find('h1')
            new_h1 = new_soup.find('h1')
            if live_h1 and new_h1:
                new_h1.string = live_h1.get_text(strip=True)

        # Author, time
        for eid in ['js_author_name_text','publish_time','js_name']:
            e1 = soup.find(id=eid); e2 = new_soup.find(id=eid)
            if e1 and e2 and e1.get_text(strip=True):
                e2.string = e1.get_text(strip=True)

        # Clean placeholder classes
        for img in new_soup.find_all('img'):
            cl = img.get('class', [])
            if isinstance(cl, str): cl = cl.split()
            nc = [c for c in cl if c not in ('js_img_placeholder','wx_img_placeholder')]
            if nc: img['class'] = ' '.join(nc)
            elif img.has_attr('class'): del img['class']

        result = str(new_soup)
        result = result.replace('大冲在思考', '沈理电协')
        result = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', result)
        result = result.replace('&amp;', '&')
        result = result.replace('<!DOCTYPE html>', '', 1) if result.count('<!DOCTYPE html>') > 1 else result

        (article_dir / 'index.html').write_text(result, 'utf-8')

        # Download cover
        if og_img_url and og_img_url.startswith('http') and is_cdn(og_img_url):
            try:
                cover_data = captured.get(og_img_url) or captured.get(og_img_url.split('?')[0])
                if not cover_data:
                    cover_result = await page.evaluate("""async (url) => {
                        try { const r = await fetch(url);
                        if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                        } catch(e) { return null; }
                    }""", og_img_url)
                    if cover_result: cover_data = bytes(cover_result)
                if cover_data and len(cover_data) > 500:
                    (article_dir / 'cover.jpg').write_bytes(cover_data)
                    logs.append(f"Cover downloaded: {len(cover_data)}B")
            except Exception as e:
                logs.append(f"Cover download failed: {e}")

        # Fix og:image
        rhtml = (article_dir / 'index.html').read_text('utf-8')
        rhtml = re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', rhtml)
        rhtml = re.sub(r'content="[^"]*"\s+property="twitter:image"', 'content="cover.jpg" property="twitter:image"', rhtml)
        (article_dir / 'index.html').write_text(rhtml, 'utf-8')

        # Cleanup unused images
        refs = set()
        for m in re.finditer(r'img_\d+\.\w+', rhtml): refs.add(m.group())
        for m in re.finditer(r'rem_\d+\.\w+', rhtml): refs.add(m.group())
        for f in sorted(article_dir.iterdir()):
            if f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp','.svg','.bmp'):
                if f.name not in refs and f.name != 'cover.jpg':
                    f.unlink()

        remote = len(re.findall(r'mmbiz\.qpic\.cn|mmecoa\.qpic\.cn', rhtml))
        logs.append(f"Done: {len(url_map)} imgs, {len(rhtml)}B, {remote} remote CDN refs")

        await browser.close()
        return True, '\n'.join(logs)

def print_menu():
    """Print the interactive menu."""
    print("\n" + "=" * 60)
    print("  WeChat Article Re-Download Tool")
    print("=" * 60)
    print()
    print("  1. Search and select article by keyword")
    print("  2. List recent 20 articles")
    print("  3. Enter WeChat URL + directory name directly")
    print("  4. Quit")
    print()

async def interactive_mode():
    """Run the tool in interactive command-line mode."""
    while True:
        print_menu()
        choice = input("Choice (1-4): ").strip()

        if choice == '4':
            print("Goodbye!")
            break

        wechat_url = None
        article_dir_name = None
        article_type = None

        if choice == '1':
            keyword = input("Search keyword: ").strip()
            results = search_articles(keyword)
            if not results:
                print("No articles found.")
                continue

            print(f"\nFound {len(results)} articles:")
            for i, (name, date, title) in enumerate(results[:30]):
                print(f"  [{i}] {date} | {title[:50]}")

            sel = input(f"\nSelect number (0-{min(len(results)-1, 29)}): ").strip()
            try:
                idx = int(sel)
                article_dir_name = results[idx][0]
                print(f"Selected: {article_dir_name}")
            except:
                print("Invalid selection.")
                continue

        elif choice == '2':
            results = list_articles()[:20]
            print(f"\nRecent 20 articles:")
            for i, (name, date, title) in enumerate(results):
                print(f"  [{i}] {date} | {title[:50]}")

            sel = input(f"\nSelect number (0-{len(results)-1}): ").strip()
            try:
                idx = int(sel)
                article_dir_name = results[idx][0]
                print(f"Selected: {article_dir_name}")
            except:
                print("Invalid selection.")
                continue

        elif choice == '3':
            article_dir_name = input("Article directory name: ").strip()
            if not article_dir_name:
                print("Directory name required.")
                continue

        else:
            print("Invalid choice.")
            continue

        wechat_url = input("\nWeChat article URL: ").strip()
        if not wechat_url or not ('mp.weixin.qq.com' in wechat_url or 'mp.weixin.qq.com' in wechat_url):
            print("Invalid WeChat URL.")
            continue

        print("\nArticle type:")
        print("  1. appmsg (standard article)")
        print("  2. share_content_page (image/article card type)")
        type_choice = input("Type (1/2): ").strip()
        article_type = 'appmsg' if type_choice == '1' else 'share_content_page'

        throttle_input = input("Bandwidth limit in KB/s (0=unlimited): ").strip()
        try:
            throttle_kbps = int(throttle_input) if throttle_input else 0
        except:
            throttle_kbps = 0

        print(f"\nRe-downloading from cloud...")
        print(f"  URL: {wechat_url[:80]}...")
        print(f"  Target: {article_dir_name}")
        print(f"  Type: {article_type}")
        if throttle_kbps > 0:
            print(f"  Bandwidth: {throttle_kbps} KB/s")
        print()

        success, msg = await download_and_replace(wechat_url, article_dir_name, article_type, throttle_kbps)
        if success:
            print("SUCCESS!")
        else:
            print("FAILED!")
        print(msg)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='WeChat Article Re-Download Tool')
    ap.add_argument('--web', action='store_true', help='Launch web UI on http://localhost:8899')
    ap.add_argument('--throttle', type=int, default=0, help='Bandwidth limit in KB/s (0=unlimited)')
    ap.add_argument('url', nargs='?', help='WeChat article URL')
    ap.add_argument('dir', nargs='?', help='Article directory name')
    ap.add_argument('type', nargs='?', choices=['appmsg', 'share'], help='Article type')
    args = ap.parse_args()

    if args.web:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading, webbrowser, traceback

        HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信文章云端重下载工具</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f5;color:#333;padding:20px}
.container{max-width:700px;margin:0 auto}
h1{text-align:center;color:#1a1a2e;margin-bottom:8px;font-size:1.4em}
.subtitle{text-align:center;color:#888;font-size:.85em;margin-bottom:24px}
.card{background:#fff;border-radius:10px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
label{display:block;font-size:.85em;font-weight:600;color:#555;margin-bottom:4px}
input,select{width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:6px;font-size:.95em;margin-bottom:12px;transition:border .2s}
input:focus,select:focus{outline:none;border-color:#4a90d9}
.row{display:flex;gap:12px}
.row>div{flex:1}
.btn{width:100%;padding:12px;border:none;border-radius:6px;font-size:1em;font-weight:600;cursor:pointer;transition:all .2s}
.btn-primary{background:#4a90d9;color:#fff}
.btn-primary:hover{background:#3a7bc8}
.btn-primary:disabled{background:#aaa;cursor:not-allowed}
.search-box{display:flex;gap:8px;margin-bottom:12px}
.search-box input{flex:1;margin-bottom:0}
.search-box button{padding:10px 16px;background:#4a90d9;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:.9em;white-space:nowrap}
#results{max-height:300px;overflow-y:auto;margin-bottom:12px}
.result-item{padding:10px 12px;border-bottom:1px solid #eee;cursor:pointer;transition:background .15s}
.result-item:hover{background:#e8f0fe}
.result-item.selected{background:#4a90d9;color:#fff}
#logs{background:#1a1a2e;color:#0f0;font-family:monospace;font-size:.82em;padding:14px;border-radius:6px;max-height:200px;overflow-y:auto;white-space:pre-wrap;margin-top:8px;display:none}
.status{text-align:center;font-weight:600;margin-top:8px;display:none}
.status.success{color:#2e7d32}
.status.fail{color:#c62828}
</style>
</head>
<body>
<div class="container">
<h1>微信文章云端重下载工具</h1>
<p class="subtitle">输入微信文章链接，选择要替换的目标文章，从云端重新拉取</p>

<div class="card">
<label>微信文章链接</label>
<input id="url" type="text" placeholder="https://mp.weixin.qq.com/s/...">

<label>选择目标文章（搜索后点击选中）</label>
<div class="search-box">
<input id="search" type="text" placeholder="输入关键词或日期搜索...">
<button onclick="doSearch()">搜索</button>
<button onclick="doRecent()" style="background:#888">最近 20 篇</button>
</div>
<div id="results" style="color:#888;padding:10px">正在加载最近文章...</div>

<label>文章类型</label>
<select id="type">
<option value="appmsg">appmsg（普通文章）</option>
<option value="share_content_page">share_content_page（图片卡片类型）</option>
</select>

<label>带宽限制（KB/s，0=不限速）</label>
<input id="throttle" type="number" value="0" min="0" max="99999" step="100" placeholder="0 = 不限速">

<button id="downloadBtn" class="btn btn-primary" onclick="doDownload()" disabled>下载并替换</button>
<div id="status" class="status"></div>
<div id="logs"></div>
</div>
</div>

<script>
var selectedDir = null;

function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

async function doSearch() {
    var q = document.getElementById('search').value.trim();
    var resp = await fetch('/api/articles' + (q ? '?q=' + encodeURIComponent(q) : ''));
    var data = await resp.json();
    renderResults(data);
}

async function doRecent() {
    var resp = await fetch('/api/recent');
    var data = await resp.json();
    renderResults(data);
}

function renderResults(data) {
    var el = document.getElementById('results');
    selectedDir = null;
    document.getElementById('downloadBtn').disabled = true;
    if (!data.length) {
        el.innerHTML = '<div style="padding:10px;color:#888">未找到匹配文章</div>';
        return;
    }
    var html = '';
    for (var i = 0; i < data.length; i++) {
        var a = data[i];
        html += '<div class="result-item" onclick="pickArticle(this, \'' + escapeHtml(a.name).replace(/'/g, "\\'") + '\')">';
        html += a.date + ' | ' + escapeHtml(a.title).substring(0, 55);
        html += '</div>';
    }
    el.innerHTML = html;
}

function pickArticle(el, name) {
    var items = document.querySelectorAll('.result-item');
    for (var i = 0; i < items.length; i++) items[i].classList.remove('selected');
    el.classList.add('selected');
    selectedDir = name;
    document.getElementById('downloadBtn').disabled = false;
}

async function doDownload() {
    var url = document.getElementById('url').value.trim();
    var type = document.getElementById('type').value;
    var throttle = parseInt(document.getElementById('throttle').value) || 0;
    if (!url || !selectedDir) return;

    var btn = document.getElementById('downloadBtn');
    var status = document.getElementById('status');
    var logs = document.getElementById('logs');
    btn.disabled = true;
    btn.textContent = '正在下载...';
    status.style.display = 'none';
    logs.style.display = 'block';
    logs.textContent = '连接中...';

    try {
        var resp = await fetch('/api/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url, dir: selectedDir, type: type, throttle: throttle})
        });
        var data = await resp.json();
        logs.textContent = data.message;
        status.style.display = 'block';
        if (data.success) {
            status.className = 'status success';
            status.textContent = '成功！文章已替换';
        } else {
            status.className = 'status fail';
            status.textContent = '失败';
        }
    } catch(e) {
        logs.textContent = 'Error: ' + e.message;
        status.style.display = 'block';
        status.className = 'status fail';
        status.textContent = '连接错误';
    }
    btn.disabled = false;
    btn.textContent = '下载并替换';
}

doRecent();
</script>
</body>
</html>"""

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/' or self.path.startswith('/?'):
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(HTML.encode('utf-8'))
                elif self.path == '/favicon.ico':
                    self.send_response(204)
                    self.end_headers()
                elif self.path.startswith('/api/articles'):
                    try:
                        q = ''
                        if '?q=' in self.path:
                            from urllib.parse import unquote
                            q = unquote(self.path.split('?q=')[1].split('&')[0])
                        results = search_articles(q)
                        import json as j
                        data = j.dumps([{'name': n, 'date': d, 'title': t} for n, d, t in results[:50]], ensure_ascii=False)
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(data.encode('utf-8'))
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode('utf-8'))
                elif self.path == '/api/recent':
                    try:
                        results = list_articles()[:20]
                        import json as j
                        data = j.dumps([{'name': n, 'date': d, 'title': t} for n, d, t in results], ensure_ascii=False)
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(data.encode('utf-8'))
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == '/api/download':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                        body = self.rfile.read(content_length).decode('utf-8')
                        import json as j
                        data = j.loads(body)
                        url = data.get('url', '')
                        dir_name = data.get('dir', '')
                        art_type = data.get('type', 'appmsg')
                        art_type = 'share_content_page' if art_type == 'share_content_page' else 'appmsg'
                        throttle = int(data.get('throttle', 0))

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        success, msg = loop.run_until_complete(
                            download_and_replace(url, dir_name, art_type, throttle)
                        )
                        loop.close()

                        resp = j.dumps({'success': success, 'message': msg}, ensure_ascii=False)
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(resp.encode('utf-8'))
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(j.dumps({'success': False, 'message': str(e)}).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                print(f"[{args[0]}]")

        print("Starting web UI at http://localhost:8899")
        print("Press Ctrl+C to stop")
        webbrowser.open('http://localhost:8899')
        server = HTTPServer(('localhost', 8899), Handler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            server.shutdown()
    elif args.url and args.dir and args.type:
        article_type = 'appmsg' if args.type == 'appmsg' else 'share_content_page'
        article_dir_name = args.dir
        
        # Try to find directory: exact match first, then by URL
        if not (BASE / article_dir_name).exists():
            found = find_dir_by_url(args.url)
            if found:
                article_dir_name = found.name
                print(f"Found by URL: {article_dir_name}")
            else:
                # Try partial match
                for d in BASE.iterdir():
                    if d.is_dir() and article_dir_name[:20] in d.name:
                        article_dir_name = d.name
                        print(f"Found by partial: {article_dir_name}")
                        break
        
        print(f"Direct mode: {article_dir_name[:60]} <- {args.url[:60]}...")
        success, msg = asyncio.run(download_and_replace(args.url, article_dir_name, article_type, args.throttle))
        print("SUCCESS!" if success else "FAILED!")
        print(msg)
    else:
        print("=" * 60)
        print("  WeChat Article Re-Download Tool")
        print("  Usage:")
        print("    python dl_tool.py --web              # Launch web UI")
        print("    python dl_tool.py                    # Interactive CLI")
        print("    python dl_tool.py <url> <dir> appmsg   # Direct mode")
        print("=" * 60)
        asyncio.run(interactive_mode())

