"""Debug: extract video data from WeChat page for videosnap."""
import asyncio, json, re
from pathlib import Path
import sys
sys.path.insert(0, str(Path('.').absolute()))

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={'width':1280,'height':800})
        cf = Path('wechat_cookies.json')
        if cf.exists(): await ctx.add_cookies(json.loads(cf.read_text()))
        page = await ctx.new_page()

        # Intercept ALL responses to find video
        all_video = []
        async def hdl(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'video' in ct or 'findermp' in url or '.mp4' in url:
                all_video.append((url[:120], len(await response.body()) if hasattr(response, 'body') else 0, ct))
                print(f'  Response: {url[:100]} ct={ct}')
        page.on('response', hdl)

        await page.goto('https://mp.weixin.qq.com/s/se4sF9Z5hBUGDwrrmzjPbg',
                         wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # Scroll
        th = await page.evaluate('document.body.scrollHeight')
        for pos in range(0, th + 300, 300):
            await page.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.1)
        await asyncio.sleep(3)

        # Get mp-common-videosnap element and ALL its attributes
        info = await page.evaluate('''() => {
            const el = document.querySelector('mp-common-videosnap');
            if (!el) return null;
            let attrs = {};
            for (let a of el.attributes) {
                attrs[a.name] = a.value.substring(0, 200);
            }
            return attrs;
        }''')
        print('mp-common-videosnap attrs:', info)

        # Search page HTML for video URLs
        html = await page.content()
        # Find JSON data
        for m in re.finditer(r'finder.*?video.*?url["\':]\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
            print('Found video URL in data:', m.group(1)[:200])

        # Look for video_url patterns
        for m in re.finditer(r'video_url["\']\s*[:=]\s*["\']([^"\']+)', html):
            print('video_url:', m.group(1)[:200])

        # Look for feed data
        for m in re.finditer(r'"finder_feed".*?"media".*?"url"\s*:\s*"([^"]+)"', html):
            print('finder_feed url:', m.group(1)[:200])

        print('\nAll video responses:')
        for u, sz, ct in all_video:
            print(f'  {u} ({sz}B) {ct}')

        await browser.close()

asyncio.run(main())
