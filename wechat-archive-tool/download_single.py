"""Single article re-download with network-response image interception + template head."""
import asyncio, os, re, json, shutil, random
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent))
from src.config import Config
from src.downloader import ArticleDownloader

# Short URL preferred per AGENTS.md (long links trigger CAPTCHA)
URL = 'https://mp.weixin.qq.com/s/5tWwUJKCVuQYr2E_crKrkw'
DIR_NAME = '2025-03-24_2.7.5_根本放不下'
ARTICLE_OUT = Path('../doc/public/wechat/articles') / DIR_NAME

def detect_ext_from_bytes(data):
    """Priority magic-byte detection, avoids false JPG for SVG/png/gif."""
    if data[:4] == b'\x89PNG': return 'png'
    if data[:3] == b'GIF': return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    return 'jpg'

def url_has_image_domain(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mpcdn', 'mmecoa.qpic.cn', 'res.wx.qq.com'])

def clean_url(url):
    url = url.split('#')[0]  # remove #imgIndex=N
    return url

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        cf = Path('wechat_cookies.json')
        if cf.exists(): await ctx.add_cookies(json.loads(cf.read_text()))

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        config = Config()
        config._data['output_dir'] = '../doc/public/wechat'
        config._data['download_videos'] = False
        dl = ArticleDownloader(page, config)

        # ── Network interception for image download ──
        cdn_data = {}  # clean_url -> bytes

        async def handle_response(response):
            url = response.url
            if not url_has_image_domain(url):
                return
            cu = clean_url(url)
            if cu in cdn_data:
                return
            try:
                body = await response.body()
                if body and len(body) > 200:
                    cdn_data[cu] = body
                    # Store both schemes: browser may request https:// but HTML may reference http://
                    if cu.startswith('https://'):
                        cdn_data['http://' + cu[8:]] = body
                    elif cu.startswith('http://'):
                        cdn_data['https://' + cu[7:]] = body
            except Exception:
                pass

        page.on('response', handle_response)

        await page.goto(URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # Scroll to trigger lazy images — use page-height-based steps
        total_height = await page.evaluate('document.body.scrollHeight')
        step = 300  # small steps to trigger lazy-load for each image
        for pos in range(0, total_height + step, step):
            await page.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.15)
        # Final scroll to absolute bottom in case new content was appended
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(2)
        await page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(1)

        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        og_title = soup.find('meta', property='og:title')
        title = og_title['content'] if og_title else 'Untitled'

        # ── Clean and extract ──
        dl._fix_image_urls(soup)
        # Do NOT use _inline_css (would bloat); template head will be applied later
        dl._clean_html(soup)

        # ── Save all intercepted images to article dir ──
        if ARTICLE_OUT.is_dir(): shutil.rmtree(str(ARTICLE_OUT))
        ARTICLE_OUT.mkdir(parents=True, exist_ok=True)

        url_map = {}  # clean_url -> local_filename
        img_idx = 0

        # Collect all CDN URLs from cleaned HTML
        all_cdn_urls = set()
        for img in soup.find_all('img'):
            src = img.get('src', '') or img.get('data-src', '')
            if url_has_image_domain(src):
                all_cdn_urls.add(clean_url(src))
        for tag in soup.find_all(style=True):
            st = tag.get('style', '')
            for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
                if url_has_image_domain(m.group(1)):
                    all_cdn_urls.add(clean_url(m.group(1)))
        for tag in soup.find_all(attrs={'data-lazy-bgimg': True}):
            u = tag.get('data-lazy-bgimg', '')
            if url_has_image_domain(u):
                all_cdn_urls.add(clean_url(u))

        print(f'\n[Image] Intercepted {len(cdn_data)} images, HTML references {len(all_cdn_urls)}')

        # Save intercepted images
        for cdn_url in list(cdn_data.keys()):
            if cdn_url not in all_cdn_urls:
                continue
            data = cdn_data[cdn_url]
            ext = detect_ext_from_bytes(data)
            img_idx += 1
            fname = f'img_{img_idx}.{ext}'
            (ARTICLE_OUT / fname).write_bytes(data)
            url_map[cdn_url] = fname

        # Fallback: download images not intercepted (e.g. from aiohttp)
        missing = all_cdn_urls - set(url_map.keys())
        if missing:
            print(f'[Image] {len(missing)} images not intercepted, trying aiohttp fallback...')
            import aiohttp
            cookies_dict = {}
            try:
                for c in await page.context.cookies():
                    if any(d in c.get('domain', '') for d in ['weixin', 'qq']):
                        cookies_dict[c['name']] = c['value']
            except:
                pass
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=5, force_close=True),
                cookies=cookies_dict,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'},
            ) as session:
                for url in missing:
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                if len(data) > 200:
                                    ext = detect_ext_from_bytes(data)
                                    img_idx += 1
                                    fname = f'img_{img_idx}.{ext}'
                                    (ARTICLE_OUT / fname).write_bytes(data)
                                    url_map[url] = fname
                    except Exception as e:
                        print(f'  Fallback failed: {url[:80]}... {e}')

        # ── Replace all CDN URLs in HTML ──
        for img in soup.find_all('img'):
            src = img.get('src', '')
            cu = clean_url(src)
            if cu in url_map:
                img['src'] = url_map[cu]
            # Also fix data-src if present
            ds = img.get('data-src', '')
            if ds and url_has_image_domain(ds):
                dc = clean_url(ds)
                if dc in url_map:
                    img['data-src'] = url_map[dc]
        for tag in soup.find_all(style=True):
            st = tag.get('style', '')
            for cdn_url, local_fname in url_map.items():
                if cdn_url in st:
                    st = st.replace(cdn_url, local_fname)
            tag['style'] = st
        for tag in soup.find_all(attrs={'data-lazy-bgimg': True}):
            bg = tag.get('data-lazy-bgimg', '')
            cu = clean_url(bg)
            if cu in url_map:
                tag['data-lazy-bgimg'] = url_map[cu]

        # Title
        for t in soup.find_all('title'):
            t.string = title
        if not soup.find('title'):
            head = soup.find('head')
            if head:
                t = soup.new_tag('title')
                t.string = title
                head.append(t)

        html_str = str(soup).replace('大冲在思考', '沈理电协')
        html_str = html_str.replace('&amp;', '&')
        # Clean filename parameter pollution
        html_str = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', html_str)
        # Final regex sweep: replace any remaining CDN URLs (catches meta tags, etc.)
        for cdn_url, local_fname in sorted(url_map.items(), key=lambda x: -len(x[0])):
            html_str = html_str.replace(cdn_url, local_fname)
            # Also catch &amp;-encoded variants
            amp_url = cdn_url.replace('&', '&amp;')
            if amp_url != cdn_url:
                html_str = html_str.replace(amp_url, local_fname)
        # Fix og:image if still pointing to CDN (handle both attribute orders)
        html_str = re.sub(
            r'<meta (?:content="http[^"]*mmbiz\.qpic\.cn[^"]*"\s+property="og:image"|property="og:image"\s+content="http[^"]*mmbiz\.qpic\.cn[^"]*")',
            '<meta property="og:image" content="cover.jpg"',
            html_str
        )
        html_str = re.sub(
            r'<meta (?:content="http[^"]*mmbiz\.qpic\.cn[^"]*"\s+property="twitter:image"|property="twitter:image"\s+content="http[^"]*mmbiz\.qpic\.cn[^"]*")',
            '<meta property="twitter:image" content="cover.jpg"',
            html_str
        )
        (ARTICLE_OUT / 'index.html').write_text(html_str, encoding='utf-8')
        print(f'Done: {len(list(ARTICLE_OUT.iterdir()))} files, {len(html_str)}B')
        await browser.close()

asyncio.run(main())
