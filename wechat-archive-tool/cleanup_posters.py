"""Download video poster images and fix remote URLs in 5 articles."""
import re, asyncio, json
from pathlib import Path
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')
TARGETS = [
    '2022-03-08_戴最可爱的发绳，造最猛的机器人！',
    '2021-05-11_欢迎宁校长莅临指导！',
    '2021-04-23_RoboMaster2021赛事简介',
    '2020-12-31_2020年终总结',
    '2020-12-25_快乐的圣诞节',
]

def detect_ext_from_bytes(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:3] == b'GIF': return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'webp'
    return 'jpg'

def url_has_image_domain(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mmecoa.qpic.cn'])

def clean_url(url):
    return url.split('#')[0]

async def cleanup_article(page, article_dir):
    html_path = article_dir / 'index.html'
    html = html_path.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')

    # Collect remote poster URLs
    remote_posters = {}
    for video in soup.find_all('video'):
        poster = video.get('poster', '')
        if url_has_image_domain(poster):
            remote_posters[clean_url(poster)] = poster

    # Also check for any remaining CDN URLs in src/img/background
    remaining_cdn = set()
    for img in soup.find_all('img'):
        for attr in ['src', 'data-src']:
            val = img.get(attr, '')
            if url_has_image_domain(val):
                remaining_cdn.add(clean_url(val))
    for tag in soup.find_all(style=True):
        st = tag.get('style', '')
        for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
            if url_has_image_domain(m.group(1)):
                remaining_cdn.add(clean_url(m.group(1)))
    for tag in soup.find_all(attrs={'data-lazy-bgimg': True}):
        bg = tag.get('data-lazy-bgimg', '')
        if url_has_image_domain(bg):
            remaining_cdn.add(clean_url(bg))

    print(f'\n{article_dir.name}:')
    print(f'  Remote posters: {len(remote_posters)}')
    print(f'  Other remote images: {len(remaining_cdn)}')

    all_urls = set(remote_posters.keys()) | remaining_cdn
    if not all_urls:
        print('  Already clean')
        return

    url_map = {}
    img_idx = len(list(article_dir.glob('img_*')))

    for url in sorted(all_urls):
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
                (article_dir / fname).write_bytes(data)
                url_map[url] = fname
                print(f'  Downloaded: {fname} ({len(data)//1024}KB)')
            else:
                print(f'  FAILED: {url[:80]}...')
        except Exception as e:
            print(f'  ERROR: {url[:80]}... {e}')

    if not url_map:
        return

    # Replace in HTML
    for video in soup.find_all('video'):
        poster = video.get('poster', '')
        cu = clean_url(poster)
        if cu in url_map:
            video['poster'] = url_map[cu]

    for img in soup.find_all('img'):
        for attr in ['src', 'data-src']:
            val = img.get(attr, '')
            cu = clean_url(val)
            if cu in url_map:
                img[attr] = url_map[cu]

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

    result = str(soup)
    result = result.replace('&amp;', '&')

    # Final sweep
    for cdn_url, local_fname in sorted(url_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(cdn_url, local_fname)
        amp_url = cdn_url.replace('&', '&amp;')
        if amp_url != cdn_url:
            result = result.replace(amp_url, local_fname)

    # Fix og:image
    result = re.sub(r'content="[^"]*mmbiz\.qpic\.cn[^"]*"', 'content="cover.jpg"', result)
    result = re.sub(r'content="[^"]*mmecoa\.qpic\.cn[^"]*"', 'content="cover.jpg"', result)

    html_path.write_text(result, encoding='utf-8')
    remaining = 1 if ('mmbiz.qpic.cn' in result or 'mmecoa.qpic.cn' in result) else 0
    print(f'  Done: {len(article_dir.iterdir())} files, remote={remaining}, {len(result)}B')

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        cf = Path('wechat_cookies.json')
        if cf.exists():
            await ctx.add_cookies(json.loads(cf.read_text()))

        page = await ctx.new_page()

        # Navigate to any wechat page first for cookies
        await page.goto('https://mp.weixin.qq.com/', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)

        for d in TARGETS:
            ad = BASE / d
            if ad.is_dir():
                await cleanup_article(page, ad)

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
