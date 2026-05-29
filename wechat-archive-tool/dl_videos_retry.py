"""Retry video download for articles 1 & 2 by navigating to CDN directly."""
import asyncio, re, json
from pathlib import Path
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')
ARTICLES = [
    ('2022-03-08_戴最可爱的发绳，造最猛的机器人！', 'https://mp.weixin.qq.com/s/cx6wRRdnZyC-f8j59tVrCQ'),
    ('2021-05-11_欢迎宁校长莅临指导！', 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'),
]

async def dl_one(page, dir_name, wechat_url):
    article_dir = BASE / dir_name
    html_path = article_dir / 'index.html'
    html = html_path.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')

    videos = soup.find_all('video')
    if not videos:
        print(f'  No video elements')
        return

    video_urls = []
    for v in videos:
        src = v.get('src', '')
        if src and 'mpvideo.qpic.cn' in src:
            video_urls.append(src)

    if not video_urls:
        print(f'  No remote video URLs')
        return

    print(f'\n{dir_name[:40]}...')

    for i, vurl in enumerate(video_urls):
        print(f'  Video URL: {vurl[:100]}...')

        # Approach 1: Navigate directly to CDN URL, capture response
        captured = {}
        async def hdl(response):
            url = response.url
            if url not in captured and len(response.url) > 10:
                try:
                    body = await response.body()
                    if body and len(body) > 50000:
                        captured[url] = body
                        print(f'    Captured via intercept: {len(body)//1024}KB')
                except:
                    pass

        page.on('response', hdl)
        try:
            await page.goto(vurl, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(3)
        except:
            pass

        # Approach 2: If not captured, use page.evaluate with direct URL navigation
        if not captured:
            print(f'    Trying page.evaluate fetch...')
            try:
                result = await page.evaluate("""async (url) => {
                    try {
                        const r = await fetch(url, {mode: 'no-cors'});
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", vurl)
                if result and len(result) > 50000:
                    data = bytes(result)
                    captured[vurl] = data
                    print(f'    Fetched: {len(result)}B')
                else:
                    print(f'    Fetch returned: {len(result) if result else "null"}')
            except Exception as e:
                print(f'    Fetch error: {e}')

        if captured:
            for c_url, c_data in captured.items():
                fname = f'video_1.mp4'
                (article_dir / fname).write_bytes(c_data)
                print(f'    Saved: {fname} ({len(c_data)//1024}KB)')

                # Update HTML
                for v in soup.find_all('video'):
                    src = v.get('src', '')
                    if 'mpvideo.qpic.cn' in src:
                        v['src'] = fname
                        v['controls'] = ''
                        break

                result_html = str(soup).replace('&amp;', '&')
                result_html = result_html.replace(vurl, fname)
                html_path.write_text(result_html, encoding='utf-8')
                print(f'    HTML updated, video remote={"mpvideo.qpic.cn" in result_html}')
                break
        else:
            print(f'  FAILED: could not download video')


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

        # First navigate to wechat to get cookies set
        await page.goto('https://mp.weixin.qq.com/', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)

        for dir_name, wechat_url in ARTICLES:
            await dl_one(page, dir_name, wechat_url)
            await asyncio.sleep(3)

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
