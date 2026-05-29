"""Debug: check if WeChat JS creates fresh video URLs on page load."""
import asyncio, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

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
        url = 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'

        # Intercept ALL responses to find video URLs
        all_urls = []
        async def hdl(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'video' in ct or 'mpvideo' in url:
                all_urls.append((url, response.status, ct))
        page.on('response', hdl)

        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # Scroll
        th = await page.evaluate('document.body.scrollHeight')
        for pos in range(0, th + 300, 300):
            await page.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.1)
        await asyncio.sleep(3)

        # Check video elements
        info = await page.evaluate('''() => {
            const videos = document.querySelectorAll('video');
            let result = [];
            videos.forEach((v, i) => {
                result.push({
                    index: i,
                    src: v.src ? v.src.substring(0, 100) : 'none',
                    poster: v.poster ? v.poster.substring(0, 80) : 'none',
                    preload: v.getAttribute('preload'),
                    readyState: v.readyState,
                    networkState: v.networkState,
                    duration: v.duration,
                    class: v.className.substring(0, 60)
                });
            });
            // Also check iframes
            const iframes = document.querySelectorAll('iframe');
            let iframeInfo = [];
            iframes.forEach(f => {
                iframeInfo.push(f.src ? f.src.substring(0, 100) : 'none');
            });
            return {videos: result, iframes: iframeInfo};
        }''')
        print('Video elements:', info['videos'])
        print('Iframes:', info['iframes'])

        # Check mpvideo elements
        mp = await page.evaluate('''() => {
            const mps = document.querySelectorAll('mpvideo, mp-common-videosnap');
            let r = [];
            mps.forEach(m => r.push({
                tag: m.tagName,
                vid: m.getAttribute('vid') || m.getAttribute('data-vid'),
                url: m.getAttribute('data-url') || m.getAttribute('src'),
            }));
            return r;
        }''')
        print('MPVideo elements:', mp)

        # Check video_iframe spans
        vfs = await page.evaluate('''() => {
            const spans = document.querySelectorAll('.video_iframe, [class*="video_iframe"]');
            let r = [];
            spans.forEach(s => r.push({
                class: s.className,
                dataSrc: (s.getAttribute('data-src') || '').substring(0, 100),
            }));
            return r;
        }''')
        print('Video_iframe spans:', vfs)

        # Try to force-load video
        await page.evaluate('''() => {
            const v = document.querySelector('video');
            if (v) {
                v.setAttribute('preload', 'auto');
                v.load();
            }
        }''')
        await asyncio.sleep(5)

        # Check again
        info2 = await page.evaluate('''() => {
            const videos = document.querySelectorAll('video');
            let result = [];
            videos.forEach((v, i) => {
                result.push({
                    index: i,
                    src: v.src ? v.src.substring(0, 100) : 'none',
                    readyState: v.readyState,
                    networkState: v.networkState,
                    duration: v.duration,
                });
            });
            return result;
        }''')
        print('After force load:', info2)

        # All intercepted video URLs
        print(f'\nIntercepted video URLs ({len(all_urls)}):')
        for u, status, ct in all_urls:
            print(f'  status={status} ct={ct} url={u[:100]}')

        await browser.close()

asyncio.run(main())
