"""
Batch re-download all articles before 2023-03-23 from WeChat cloud.
Single browser session, rotating context per article for fresh fingerprint.
Resumable, CAPTCHA-aware, zero subprocess overhead.
"""
import asyncio, json, re, sys, time, os, random
from pathlib import Path
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

BASE = Path(__file__).parent.parent / 'doc' / 'public' / 'wechat' / 'articles'
TOOL_DIR = Path(__file__).parent
PROGRESS_FILE = TOOL_DIR / 'batch_re_dl_progress.json'
FAILED_FILE = TOOL_DIR / 'batch_re_dl_failed.json'
LOG_FILE = TOOL_DIR / 'batch_re_dl_log.txt'
CONFIG_FILE = TOOL_DIR / 'config.json'
COOKIES = TOOL_DIR / 'wechat_cookies.json'

CUTOFF = datetime(2024, 2, 3)
START_DATE = datetime(2023, 3, 7)
THROTTLE_KBPS = 0
DELAY_SECONDS = 10
CAPTCHA_COOLDOWN = 1800
MAX_CONSECUTIVE_CAPTCHA = 5

UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
]

def load_json(path):
    if path.exists():
        try: return json.loads(path.read_text('utf-8'))
        except: pass
    return {}

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')

class Logger:
    def __init__(self, path):
        self.path = path
    def __call__(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        print(line)
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
log = Logger(LOG_FILE)

def extract_url(html_path):
    try:
        text = html_path.read_text('utf-8')[:20000]
    except:
        try: text = html_path.read_text('gbk')[:20000]
        except: text = html_path.read_text('utf-8', errors='ignore')[:20000]
    m = re.search(r'<meta\s[^>]*property="og:url"\s[^>]*content="([^"]+)"', text)
    if not m:
        m = re.search(r'<meta\s[^>]*content="([^"]+)"\s[^>]*property="og:url"', text)
    return m.group(1) if m else None

def extract_dir_date(dirname):
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_', dirname)
    return datetime.strptime(m.group(1), '%Y-%m-%d') if m else None

def is_cdn(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mmecoa.qpic.cn', 'mpcdn', 'res.wx.qq.com'])

def detect_ext(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:6] in (b'GIF89a', b'GIF87a'): return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    return 'jpg'

def load_protected():
    return set(load_json(CONFIG_FILE).get('protected_articles', []))

def build_article_list():
    protected = load_protected()
    articles = []
    for d in sorted(BASE.iterdir()):
        if not d.is_dir() or d.name.startswith('_'):
            continue
        dt = extract_dir_date(d.name)
        if not dt or dt >= CUTOFF or dt < START_DATE:
            continue
        if d.name in protected:
            continue
        html = d / 'index.html'
        if not html.exists():
            continue
        url = extract_url(html)
        if not url:
            log(f'SKIP {d.name}: no og:url')
            continue
        articles.append((d.name, url, d))
    return articles

def load_templates():
    templates = {}
    for d in BASE.iterdir():
        if d.is_dir() and '冬日畅言' in d.name:
            templates['appmsg'] = (d / 'index.html').read_text('utf-8')
        if d.is_dir() and '小雪伊始' in d.name:
            templates['share_content_page'] = (d / 'index.html').read_text('utf-8')
    return templates

async def process_one(page, captured, template_html, article_dir, wechat_url):
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    logs = []
    captured.clear()

    logs.append(f"Opening: {wechat_url[:80]}...")
    try:
        await page.goto(wechat_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)
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
        return False, f"Failed to load page: {e}"

    soup = BeautifulSoup(html, 'lxml')
    js = soup.find(id='js_content')

    # Detect permanently broken pages (deleted, violation, etc.)
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else ''
    BROKEN_KEYWORDS = ['违规', '删除', '投诉', '涉嫌侵权', '已注销',
                       '此内容', '该页面', '此账号', '已被', '不存在', '已失效']
    if any(kw in page_title for kw in BROKEN_KEYWORDS):
        return False, f"broken page: {page_title[:100]}"

    if not js or len(str(js)) < 2000:
        # Check if page has error structure (not CAPTCHA)
        if any(kw in html[:50000] for kw in BROKEN_KEYWORDS):
            return False, f"broken page (body): {page_title[:100]}"
        return False, "empty js_content"

    logs.append(f"Content: {len(str(js))} chars, {len(js.find_all('img'))} imgs, {len(captured)} imgs captured")

    og_img = soup.find('meta', property='og:image')
    og_img_url = og_img['content'] if og_img and og_img.get('content') else None
    logs.append(f"Cover URL: {og_img_url[:80] if og_img_url else 'N/A'}")

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

    for f in article_dir.glob('img_*'): f.unlink()
    for f in article_dir.glob('rem_*'): f.unlink()

    captured_normalized = {}
    for k, v in captured.items():
        base = k.split('?')[0].split('#')[0]
        captured_normalized[base] = v
        if base.startswith('http://'):
            captured_normalized[base.replace('http://', 'https://')] = v
        elif base.startswith('https://'):
            captured_normalized[base.replace('https://', 'http://')] = v

    url_map = {}
    for url in sorted(all_urls):
        base = url.split('?')[0].split('#')[0]
        data = captured_normalized.get(base) or captured.get(url) or captured.get(url.split('?')[0])
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

    normalized_map = {}
    for cdn, loc in url_map.items():
        base = cdn.split('?')[0].split('#')[0]
        normalized_map[base] = loc
        if base.startswith('http://'):
            normalized_map[base.replace('http://', 'https://')] = loc
        elif base.startswith('https://'):
            normalized_map[base.replace('https://', 'http://')] = loc

    def match_url(html_url):
        base = html_url.split('?')[0].split('#')[0]
        if base in normalized_map: return normalized_map[base]
        if base.startswith('https://'):
            b2 = base[8:]
            if b2 in normalized_map: return normalized_map[b2]
        if base.startswith('http://'):
            b2 = base[7:]
            if b2 in normalized_map: return normalized_map[b2]
        return None

    for img in js.find_all('img'):
        for attr in ['src', 'data-src']:
            val = img.get(attr, '')
            if val and is_cdn(val):
                val = ('https:' + val) if val.startswith('//') else val
                loc = match_url(val)
                if loc: img[attr] = loc
        st = img.get('style', '')
        if st:
            for cdn, loc in url_map.items():
                if cdn in st: st = st.replace(cdn, loc)
            img['style'] = st

    for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
        bg = tag.get('data-lazy-bgimg', '')
        if bg:
            loc = match_url(bg)
            if loc: tag['data-lazy-bgimg'] = loc

    for tag in js.find_all(style=True):
        st = tag.get('style', '')
        changed = False
        for m in re.finditer(r'url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
            url = m.group(1)
            loc = match_url(url)
            if loc:
                st = st.replace(url, loc)
                changed = True
        if changed: tag['style'] = st

    new_soup = BeautifulSoup(template_html, 'lxml')

    for meta_name, attr in [('og:title','property'),('og:url','property'),
                             ('og:description','property'),('og:site_name','property'),
                             ('og:type','property'),('og:article:author','property'),
                             ('twitter:title','property'),('twitter:site','property'),
                             ('twitter:creator','property'),('twitter:description','property'),
                             ('twitter:card','property'),('description','name'),('author','name')]:
        src = soup.find('meta', attrs={attr: meta_name})
        dst = new_soup.find('meta', attrs={attr: meta_name})
        if src and dst and src.get('content'): dst['content'] = src['content']

    ti = new_soup.find('title')
    og_ti = soup.find('meta', property='og:title')
    if ti and og_ti and og_ti.get('content'): ti.string = og_ti['content']

    nj = new_soup.find(id='js_content')
    if nj:
        nj.clear()
        for c in list(js.contents):
            try: nj.append(c)
            except:
                cc = BeautifulSoup(str(c), 'lxml').find()
                if cc: nj.append(cc)

    h1 = soup.find(id='activity-name')
    nh = new_soup.find(id='activity-name')
    if h1 and nh:
        nh.clear()
        sp = new_soup.new_tag('span')
        sp['class'] = 'js_title_inner'
        sp.string = h1.get_text(strip=True) or (og_ti['content'] if og_ti else '')
        nh.append(sp)
    if not (h1 and nh):
        live_h1 = soup.find('h1')
        new_h1 = new_soup.find('h1')
        if live_h1 and new_h1:
            new_h1.string = live_h1.get_text(strip=True)

    for eid in ['js_author_name_text','publish_time','js_name']:
        e1 = soup.find(id=eid); e2 = new_soup.find(id=eid)
        if e1 and e2 and e1.get_text(strip=True): e2.string = e1.get_text(strip=True)

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
                logs.append(f"Cover: {len(cover_data)}B")
        except Exception as e:
            logs.append(f"Cover failed: {e}")

    rhtml = (article_dir / 'index.html').read_text('utf-8')
    rhtml = re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', rhtml)
    rhtml = re.sub(r'content="[^"]*"\s+property="twitter:image"', 'content="cover.jpg" property="twitter:image"', rhtml)
    (article_dir / 'index.html').write_text(rhtml, 'utf-8')

    refs = set()
    for m in re.finditer(r'img_\d+\.\w+', rhtml): refs.add(m.group())
    for m in re.finditer(r'rem_\d+\.\w+', rhtml): refs.add(m.group())
    for f in sorted(article_dir.iterdir()):
        if f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp','.svg','.bmp'):
            if f.name not in refs and f.name != 'cover.jpg':
                f.unlink()

    remote = len(re.findall(r'mmbiz\.qpic\.cn|mmecoa\.qpic\.cn', rhtml))
    logs.append(f"Done: {len(url_map)} imgs, {len(rhtml)}B, {remote} remote refs")

    return True, '\n'.join(logs)

async def batch_main(remaining):
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    templates = load_templates()
    if 'appmsg' not in templates:
        log('ERROR: appmsg template not found')
        return

    template_html = templates['appmsg']
    progress = load_json(PROGRESS_FILE)
    failed_store = load_json(FAILED_FILE)
    total_start = len(progress)
    total_rem = len(remaining)

    async def launch_browser(pw):
        args = [
            f'--window-size={random.randint(1024,1920)},{random.randint(768,1080)}',
            f'--disable-features={random.choice(["Translate","OptimizationHints","PrivacySandbox","InterestFeed"])}',
        ]
        return await pw.chromium.launch(headless=False, args=args)

    captcha_streak = 0
    CONTEXT_ROTATE = 30  # rotate context every N articles

    async with async_playwright() as p:
        browser = await launch_browser(p)

        async def fresh_context(_browser):
            ua = random.choice(UA_POOL)
            vw = random.randint(1024, 1920)
            vh = random.randint(768, 1080)
            _ctx = await _browser.new_context(
                user_agent=ua,
                viewport={'width': vw, 'height': vh}
            )
            # Cookies skipped - flagged session
            # try:
            #     if COOKIES.exists():
            #         await _ctx.add_cookies(json.loads(COOKIES.read_text()))
            # except: pass
            _page = await _ctx.new_page()
            st = Stealth(chrome_runtime=True, navigator_plugins=True)
            await st.apply_stealth_async(_page)
            return _ctx, _page

        ctx, page = await fresh_context(browser)
        since_rotate = 0

        idx = 0
        while idx < len(remaining):
            dirname, url, article_dir = remaining[idx]
            n_progress = len(progress)
            log(f'[{n_progress - total_start + idx + 1}/{total_rem + n_progress - total_start}] {dirname}')

            captured = {}
            async def hdl(response):
                url_r = response.url
                if response.status == 200 and is_cdn(url_r):
                    try:
                        body = await response.body()
                        if body and len(body) > 200:
                            captured[url_r] = body
                            captured[url_r.split('?')[0]] = body
                    except: pass
            page.on('response', hdl)

            try:
                success, msg = await process_one(page, captured, template_html, article_dir, url)
            except Exception as e:
                success, msg = False, str(e)

            if success:
                log(f'  OK')
                progress[dirname] = datetime.now().isoformat()
                save_json(PROGRESS_FILE, progress)
                captcha_streak = 0
                since_rotate += 1
                idx += 1
            elif 'empty js_content' in msg.lower():
                captcha_streak += 1
                log(f'  CAPTCHA? (streak {captcha_streak}/{MAX_CONSECUTIVE_CAPTCHA})')
                if captcha_streak >= MAX_CONSECUTIVE_CAPTCHA:
                    log(f'  >> Cooldown {CAPTCHA_COOLDOWN}s, restarting browser...')
                    await page.close()
                    await ctx.close()
                    await browser.close()
                    time.sleep(CAPTCHA_COOLDOWN)
                    browser = await launch_browser(p)
                    ctx, page = await fresh_context(browser)
                    since_rotate = 0
                    log(f'  >> New browser launched, retrying...')
                    captcha_streak = 0
                    continue
                else:
                    failed_store[dirname] = 'captcha'
                    save_json(FAILED_FILE, failed_store)
                    idx += 1
                    since_rotate += 1
            else:
                log(f'  FAIL: {msg[:200]}')
                failed_store[dirname] = msg[:200]
                save_json(FAILED_FILE, failed_store)
                captcha_streak = 0
                since_rotate += 1
                idx += 1

            # Rotate context periodically for fresh fingerprint
            if since_rotate >= CONTEXT_ROTATE:
                await page.close()
                await ctx.close()
                ctx, page = await fresh_context(browser)
                since_rotate = 0

            if idx < len(remaining):
                time.sleep(DELAY_SECONDS)

        await page.close()
        await ctx.close()
        await browser.close()

    final_progress = len(load_json(PROGRESS_FILE))
    final_failed = len(load_json(FAILED_FILE))
    log(f'=== DONE: {final_progress}, Failed: {final_failed} ===')
    if final_failed:
        log(f'Failed list: {FAILED_FILE}')

def main():
    dry_run = '--dry-run' in sys.argv
    all_articles = build_article_list()
    total = len(all_articles)
    progress = load_json(PROGRESS_FILE)
    failed_store = load_json(FAILED_FILE)
    done = set(progress.keys()) | set(failed_store.keys())
    remaining = [(n, u, d) for n, u, d in all_articles if n not in done]

    est_seconds = len(remaining) * (10 + DELAY_SECONDS)  # ~10s per article
    log(f'=== Batch Re-Download ===')
    log(f'  Total: {total} | Done: {len(progress)} | Failed: {len(failed_store)} | Remaining: {len(remaining)}')
    log(f'  Throttle: {THROTTLE_KBPS} KB/s | Delay: {DELAY_SECONDS}s | Estimated: ~{timedelta(seconds=est_seconds)}')

    if dry_run:
        log('DRY RUN:')
        for n, u, d in remaining[:10]:
            log(f'  {n} -> {u[:60]}')
        if len(remaining) > 10:
            log(f'  ... and {len(remaining)-10} more')
        return

    if not remaining:
        log('All done.')
        return

    asyncio.run(batch_main(remaining))

if __name__ == '__main__':
    main()
