"""
Fix missing/abnormal cover images for articles.
Scans, downloads missing covers from live WeChat pages, reports issues.
"""
import asyncio, re, sys, time, random
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent / 'doc' / 'public' / 'wechat' / 'articles'
CUTOFF = datetime(2024, 2, 3)
MIN_COVER_BYTES = 500

UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
]

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

def extract_meta(html, name):
    # Try both attribute orders
    m = re.search(f'<meta\\s[^>]*property="{name}"\\s[^>]*content="([^"]+)"', html)
    if not m:
        m = re.search(f'<meta\\s[^>]*content="([^"]+)"\\s[^>]*property="{name}"', html)
    return m.group(1) if m else None

def build_list():
    articles = []
    for d in sorted(BASE.iterdir()):
        if not d.is_dir() or d.name.startswith('_'):
            continue
        dt = extract_dir_date(d.name)
        if not dt or dt >= CUTOFF:
            continue
        html = d / 'index.html'
        if not html.exists():
            continue
        cover = d / 'cover.jpg'
        size = cover.stat().st_size if cover.exists() else 0
        if size >= MIN_COVER_BYTES:
            continue
        h = html.read_text('utf-8', errors='ignore')[:30000]
        wechat_url = extract_meta(h, 'og:url')
        og_img = extract_meta(h, 'og:image')
        title = extract_meta(h, 'og:title') or ''
        articles.append((d, wechat_url, og_img, title, size))
    return articles

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    articles = build_list()
    print(f'Missing/abnormal covers: {len(articles)}')

    if not articles:
        print('All covers OK.')
        return

    for name, _, og, _, size in articles:
        n = name.name
        print(f'  {n[:50]:50s} cover={size}B  og={(og or "NONE")[:60]}')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=[
            f'--window-size={random.randint(1024,1920)},{random.randint(768,1080)}',
        ])
        ctx = await browser.new_context(
            user_agent=random.choice(UA_POOL),
            viewport={'width': random.randint(1024, 1920), 'height': random.randint(768, 1080)}
        )
        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        ok = 0
        failed = []

        for i, (article_dir, wechat_url, og_img, title, cover_size) in enumerate(articles):
            print(f'[{i+1}/{len(articles)}] {article_dir.name[:45]}')

            cover_url = None

            # If og:image is a CDN URL, download directly
            if og_img and is_cdn(og_img):
                cover_url = og_img.replace('http://', 'https://')

            # If og:image is local (cover.jpg) or missing, fetch from live page
            if not cover_url and wechat_url:
                print(f'  Fetching from live page...')
                try:
                    await page.goto(wechat_url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(3)
                    live_html = await page.content()
                    live_og = extract_meta(live_html, 'og:image')
                    if live_og and is_cdn(live_og):
                        live_og = live_og.replace('http://', 'https://')
                        cover_url = live_og
                        print(f'  Live cover: {cover_url[:80]}')
                    else:
                        print(f'  No CDN cover on live page: {live_og}')
                except Exception as e:
                    print(f'  Page load failed: {e}')

            if not cover_url:
                failed.append((article_dir.name, 'no cover URL found'))
                continue

            # Download cover
            try:
                result = await page.evaluate("""async (url) => {
                    try { const r = await fetch(url);
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", cover_url)
                if result and len(result) > MIN_COVER_BYTES:
                    data = bytes(result)
                    ext = detect_ext(data)
                    cover_path = article_dir / f'cover.{ext}'
                    cover_path.write_bytes(data)
                    # Update HTML og:image
                    html = (article_dir / 'index.html').read_text('utf-8')
                    html = re.sub(r'content="[^"]*"\s+property="og:image"', f'content="cover.{ext}" property="og:image"', html)
                    html = re.sub(r'content="[^"]*"\s+property="twitter:image"', f'content="cover.{ext}" property="twitter:image"', html)
                    (article_dir / 'index.html').write_text(html, 'utf-8')
                    ok += 1
                    print(f'  OK: {len(data)}B ({ext})')
                else:
                    failed.append((article_dir.name, f'download too small: {len(result) if result else 0}B'))
            except Exception as e:
                failed.append((article_dir.name, str(e)[:100]))

            time.sleep(1)

        await page.close()
        await ctx.close()
        await browser.close()

    print(f'\n=== Results ===')
    print(f'Fixed: {ok}')
    if failed:
        print(f'Failed ({len(failed)}):')
        for name, reason in failed:
            print(f'  {name}: {reason}')

if __name__ == '__main__':
    asyncio.run(main())
