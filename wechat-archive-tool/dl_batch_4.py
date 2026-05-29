"""Batch re-download 4 articles with network-response image interception."""
import asyncio, os, re, json, shutil, time
from pathlib import Path
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent))
from src.config import Config
from src.downloader import ArticleDownloader

ARTICLES = [
    ('https://mp.weixin.qq.com/s/cx6wRRdnZyC-f8j59tVrCQ', '2022-03-08_戴最可爱的发绳，造最猛的机器人！'),
    ('https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g', '2021-05-11_欢迎宁校长莅临指导！'),
    ('https://mp.weixin.qq.com/s/FBw03JxseIz9fcoU1nqx3Q', '2021-04-23_RoboMaster2021赛事简介'),
    ('https://mp.weixin.qq.com/s/DygKuBiP7yaIOt6DK3WI2g', '2020-12-31_2020年终总结'),
]

ARTICLE_BASE = Path('../doc/public/wechat/articles')

def detect_ext_from_bytes(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:3] == b'GIF': return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    return 'jpg'

def url_has_image_domain(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mpcdn', 'mmecoa.qpic.cn', 'res.wx.qq.com'])

def is_video_cdn(u):
    return any(d in u for d in ['video.qq.com', 'findermp.video.qq.com',
                                  'mpvideo.qpic.cn', 'vweixinfinder.video.qq.com'])

def clean_url(url):
    return url.split('#')[0]

async def download_one(page, dl, url, dir_name, idx, total):
    article_out = ARTICLE_BASE / dir_name
    print(f'\n[{idx}/{total}] {dir_name[:50]}')
    print(f'  URL: {url}')

    cdn_data = {}
    video_data = {}  # clean_url -> bytes (video)

    async def handle_response(response):
        u = response.url
        cu = clean_url(u)
        # Image interception
        if url_has_image_domain(u):
            if cu in cdn_data:
                return
            try:
                body = await response.body()
                if body and len(body) > 200:
                    cdn_data[cu] = body
                    if cu.startswith('https://'):
                        cdn_data['http://' + cu[8:]] = body
                    elif cu.startswith('http://'):
                        cdn_data['https://' + cu[7:]] = body
            except Exception:
                pass
            return
        # Video interception
        ct = response.headers.get('content-type', '')
        if 'video' in ct or is_video_cdn(u):
            if cu in video_data:
                return
            try:
                body = await response.body()
                if body and len(body) > 50000:
                    video_data[cu] = body
                    print(f'    [Video] Captured {len(body)}B from {u[:80]}')
            except Exception:
                pass

    page.on('response', handle_response)

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        print(f'  ERROR: page load failed: {e}')
        return False

    await asyncio.sleep(2)
    # scroll for lazy images
    total_height = await page.evaluate('document.body.scrollHeight')
    step = 300
    for pos in range(0, total_height + step, step):
        await page.evaluate(f'window.scrollTo(0, {pos})')
        await asyncio.sleep(0.15)
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await asyncio.sleep(2)
    await page.evaluate('window.scrollTo(0, 0)')
    await asyncio.sleep(1)

    # Give user time to trigger video loading
    print('  Waiting 30s for user to trigger videos...')
    await asyncio.sleep(30)

    html = await page.content()
    soup = BeautifulSoup(html, 'lxml')

    og_title = soup.find('meta', property='og:title')
    title = og_title['content'] if og_title else 'Untitled'

    # Get og:image URL before _clean_html potentially modifies meta
    og_image = soup.find('meta', property='og:image')
    og_image_url = og_image['content'] if og_image else None

    dl._fix_image_urls(soup)
    dl._clean_html(soup)

    # Clean article dir
    if article_out.is_dir():
        shutil.rmtree(str(article_out))
    article_out.mkdir(parents=True, exist_ok=True)

    # Collect CDN URLs from cleaned HTML
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

    print(f'  Intercepted: {len(cdn_data)} images, HTML refs: {len(all_cdn_urls)}')

    # Save intercepted images
    url_map = {}
    img_idx = 0
    for cdn_url in sorted(cdn_data.keys()):
        if cdn_url not in all_cdn_urls:
            continue
        data = cdn_data[cdn_url]
        ext = detect_ext_from_bytes(data)
        img_idx += 1
        fname = f'img_{img_idx}.{ext}'
        (article_out / fname).write_bytes(data)
        url_map[cdn_url] = fname

    # Fallback: download missing images via page.evaluate fetch
    missing = all_cdn_urls - set(url_map.keys())
    if missing:
        print(f'  {len(missing)} images not intercepted, trying fetch fallback...')
        for url in list(missing):
            try:
                result = await page.evaluate("""async (url) => {
                    try {
                        const r = await fetch(url);
                        if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", url)
                if result and len(result) > 200:
                    data = bytes(result)
                    ext = detect_ext_from_bytes(data)
                    img_idx += 1
                    fname = f'img_{img_idx}.{ext}'
                    (article_out / fname).write_bytes(data)
                    url_map[url] = fname
            except Exception as e:
                print(f'    Fetch fallback failed: {url[:80]}... {e}')

    # Replace CDN URLs in HTML
    for img in soup.find_all('img'):
        src = img.get('src', '')
        cu = clean_url(src)
        if cu in url_map:
            img['src'] = url_map[cu]
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

    # Save captured videos
    if video_data:
        vid_idx = 0
        for vurl, vdata in sorted(video_data.items(), key=lambda x: -len(x[1])):
            vid_idx += 1
            vfname = f'video_{vid_idx}.mp4'
            (article_out / vfname).write_bytes(vdata)
            print(f'  Video saved: {vfname} ({len(vdata)//1024}KB)')

    # Download cover image
    if og_image_url and url_has_image_domain(og_image_url):
        try:
            cover_data = cdn_data.get(clean_url(og_image_url))
            if not cover_data:
                result = await page.evaluate("""async (url) => {
                    try {
                        const r = await fetch(url);
                        if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", og_image_url)
                if result and len(result) > 200:
                    cover_data = bytes(result)
            if cover_data:
                (article_out / 'cover.jpg').write_bytes(cover_data)
                print(f'  Cover saved ({len(cover_data)}B)')
        except Exception as e:
            print(f'  Cover download failed: {e}')

    html_str = str(soup).replace('大冲在思考', '沈理电协')
    html_str = html_str.replace('&amp;', '&')
    html_str = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', html_str)

    # Final sweep: replace any remaining CDN URLs
    for cdn_url, local_fname in sorted(url_map.items(), key=lambda x: -len(x[0])):
        html_str = html_str.replace(cdn_url, local_fname)
        amp_url = cdn_url.replace('&', '&amp;')
        if amp_url != cdn_url:
            html_str = html_str.replace(amp_url, local_fname)

    # Fix og:image to local cover.jpg (handle both attribute orders)
    html_str = re.sub(
        r'<meta (?:content="http[^"]*mmbiz\.qpic\.cn[^"]*"\s+property="og:image"|property="og:image"\s+content="http[^"]*mmbiz\.qpic\.cn[^"]*")',
        '<meta property="og:image" content="cover.jpg"',
        html_str
    )
    html_str = re.sub(
        r'<meta (?:content="http[^"]*mmecoa\.qpic\.cn[^"]*"\s+property="og:image"|property="og:image"\s+content="http[^"]*mmecoa\.qpic\.cn[^"]*")',
        '<meta property="og:image" content="cover.jpg"',
        html_str
    )
    html_str = re.sub(
        r'<meta (?:content="http[^"]*qpic\.cn[^"]*"\s+property="twitter:image"|property="twitter:image"\s+content="http[^"]*qpic\.cn[^"]*")',
        '<meta property="twitter:image" content="cover.jpg"',
        html_str
    )

    (article_out / 'index.html').write_text(html_str, encoding='utf-8')
    file_count = len(list(article_out.iterdir()))
    vcount = len(video_data)
    print(f'  Done: {file_count} files ({vcount} videos), {len(html_str)}B')
    return True

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        cf = Path('wechat_cookies.json')
        if cf.exists():
            await ctx.add_cookies(json.loads(cf.read_text()))

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        config = Config()
        config._data['output_dir'] = '../doc/public/wechat'
        config._data['download_videos'] = False
        dl = ArticleDownloader(page, config)

        ok = fail = 0
        for i, (url, dir_name) in enumerate(ARTICLES, 1):
            try:
                result = await download_one(page, dl, url, dir_name, i, len(ARTICLES))
                if result:
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                print(f'  UNEXPECTED ERROR: {e}')
                fail += 1

            if i < len(ARTICLES):
                print('  Waiting 5s before next article...')
                await asyncio.sleep(5)

        print(f'\n=== DONE: {ok} OK, {fail} FAIL ===')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
