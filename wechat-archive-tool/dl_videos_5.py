"""Download videos for the 5 articles via network interception."""
import asyncio, re, json
from pathlib import Path
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')
ARTICLES = [
    ('2022-03-08_戴最可爱的发绳，造最猛的机器人！', 'https://mp.weixin.qq.com/s/cx6wRRdnZyC-f8j59tVrCQ'),
    ('2021-05-11_欢迎宁校长莅临指导！', 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'),
    ('2021-04-23_RoboMaster2021赛事简介', 'https://mp.weixin.qq.com/s/FBw03JxseIz9fcoU1nqx3Q'),
    ('2020-12-31_2020年终总结', 'https://mp.weixin.qq.com/s/DygKuBiP7yaIOt6DK3WI2g'),
    ('2020-12-25_快乐的圣诞节', 'https://mp.weixin.qq.com/s/csrzlEYzR1Uxw1ABVkOX2g'),
]

async def download_videos_for_article(page, ctx, dir_name, wechat_url):
    article_dir = BASE / dir_name
    html_path = article_dir / 'index.html'
    html = html_path.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')

    # Find video elements
    videos = soup.find_all('video')
    if not videos:
        print(f'  No video elements found')
        return

    print(f'\n  {dir_name[:40]}...')
    print(f'  Video elements: {len(videos)}')

    # Extract video src URLs
    video_urls = []
    for v in videos:
        src = v.get('src', '')
        if src:
            video_urls.append(src)

    if not video_urls:
        print(f'  No video src URLs')
        return

    # Navigate to article page for proper cookies/referer
    captured = {}
    async def handle_response(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'video' in ct or 'mpvideo.qpic.cn' in url or 'video.qq.com' in url:
            try:
                body = await response.body()
                if body and len(body) > 50000:
                    captured[url] = body
                    print(f'    Captured: {len(body)//1024}KB')
            except:
                pass

    # Navigate to article
    try:
        await page.goto(wechat_url, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        print(f'  Page load failed: {e}')

    await asyncio.sleep(3)

    # Scroll to bottom
    th = await page.evaluate('document.body.scrollHeight')
    for pos in range(0, th + 300, 300):
        await page.evaluate(f'window.scrollTo(0, {pos})')
        await asyncio.sleep(0.15)

    # Register response handler AFTER page is loaded
    page.on('response', handle_response)

    # Click video_iframe elements to trigger video loading
    await page.evaluate('''
        document.querySelectorAll('.video_iframe, .js_video_channel_container').forEach(el => {
            el.click();
        });
    ''')
    await asyncio.sleep(5)

    # Also try to open video player pages
    live_html = await page.content()
    live_soup = BeautifulSoup(live_html, 'lxml')
    for vf in live_soup.find_all('span', class_='video_iframe'):
        data_src = vf.get('data-src', '')
        if data_src:
            print(f'    Opening player: {data_src[:60]}...')
            vp = await ctx.new_page()
            try:
                await vp.goto(data_src, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(8)
                await vp.close()
            except:
                await vp.close()

    # If videos weren't captured by network, try direct fetch from page context
    if not captured:
        for vurl in video_urls:
            print(f'    Trying fetch: {vurl[:80]}...')
            try:
                result = await page.evaluate("""async (url) => {
                    try {
                        const r = await fetch(url);
                        if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", vurl)
                if result and len(result) > 50000:
                    captured[vurl] = bytes(result)
                    print(f'    Fetched: {len(result)}B')
            except Exception as e:
                print(f'    Fetch failed: {e}')

    if not captured:
        print(f'  No videos captured')
        return

    # Save videos and update HTML
    vid_idx = 0
    url_map = {}
    for vurl, vdata in sorted(captured.items(), key=lambda x: -len(x[1])):
        vid_idx += 1
        fname = f'video_{vid_idx}.mp4'
        (article_dir / fname).write_bytes(vdata)
        url_map[vurl] = fname
        print(f'    Saved: {fname} ({len(vdata)//1024}KB)')

    # Update HTML: replace video src with local file
    for v in soup.find_all('video'):
        src = v.get('src', '')
        if src in url_map:
            v['src'] = url_map[src]
            v['controls'] = ''
            print(f'    Replaced src: {url_map[src]}')

    result_html = str(soup)
    result_html = result_html.replace('&amp;', '&')

    # Final sweep
    for vurl, fname in url_map.items():
        result_html = result_html.replace(vurl, fname)

    html_path.write_text(result_html, encoding='utf-8')
    remote = 'mpvideo.qpic.cn' in result_html
    print(f'  Done: {len(list(article_dir.iterdir()))} files, video remote={remote}')


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

        for dir_name, wechat_url in ARTICLES:
            await download_videos_for_article(page, ctx, dir_name, wechat_url)
            await asyncio.sleep(3)

        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
