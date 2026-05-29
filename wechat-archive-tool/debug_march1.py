"""Debug: check video elements on 2022-03-01 page."""
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
        await page.goto('https://mp.weixin.qq.com/s/se4sF9Z5hBUGDwrrmzjPbg',
                         wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        info = await page.evaluate('''() => {
            let result = {};
            result.videos = document.querySelectorAll('video').length;
            result.videoIframes = document.querySelectorAll('.video_iframe').length;
            result.mpVideos = document.querySelectorAll('mpvideo, mp-common-videosnap').length;
            result.iframes = document.querySelectorAll('iframe').length;

            // Check for video-related elements
            let vfInfo = [];
            document.querySelectorAll('.video_iframe').forEach(vf => {
                vfInfo.push({
                    dataSrc: (vf.getAttribute('data-src') || '').substring(0, 100),
                    dataMpvid: vf.getAttribute('data-mpvid'),
                    dataUrl: (vf.getAttribute('data-url') || '').substring(0, 100),
                });
            });
            result.vfDetails = vfInfo;

            // Check for iframe src
            let ifrInfo = [];
            document.querySelectorAll('iframe').forEach(f => {
                ifrInfo.push(f.src.substring(0, 120));
            });
            result.iframeSrcs = ifrInfo;

            // Check mp-common-videosnap
            let mpInfo = [];
            document.querySelectorAll('mp-common-videosnap').forEach(m => {
                mpInfo.push({
                    dataUrl: (m.getAttribute('data-url') || '').substring(0, 120),
                    dataSrc: (m.getAttribute('data-src') || '').substring(0, 120),
                });
            });
            result.mpDetails = mpInfo;

            return result;
        }''')
        print(info)
        await browser.close()

asyncio.run(main())
