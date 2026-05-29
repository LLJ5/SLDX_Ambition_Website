"""Try to trigger video by deeply interacting with WeChat's video player DOM."""
import asyncio, re, json
from pathlib import Path
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')

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

        targets = [
            ('2021-05-11_欢迎宁校长莅临指导！', 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'),
            ('2021-04-23_RoboMaster2021赛事简介', 'https://mp.weixin.qq.com/s/FBw03JxseIz9fcoU1nqx3Q'),
        ]

        for dir_name, article_url in targets:
            article_dir = BASE / dir_name
            print(f'\n=== {dir_name[:40]} ===', flush=True)

            captured = {}
            async def hdl(response):
                url = response.url
                ct = response.headers.get('content-type', '')
                if ('video' in ct or 'mpvideo.qpic.cn' in url) and url not in captured:
                    try:
                        body = await response.body()
                        if body and len(body) > 100000:
                            captured[url] = body
                            print(f'  Captured: {len(body)//1024}KB')
                    except:
                        pass

            page = await ctx.new_page()

            # Capture from ALL pages (including popups)
            ctx.on('page', lambda p: p.on('response', hdl))
            page.on('response', hdl)

            await page.goto(article_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            # Scroll to ensure video area is visible
            th = await page.evaluate('document.body.scrollHeight')
            for pos in range(0, th + 200, 200):
                await page.evaluate(f'window.scrollTo(0, {pos})')
                await asyncio.sleep(0.1)

            await asyncio.sleep(2)

            # Aggressively try to trigger the video
            result = await page.evaluate('''() => {
                let logs = [];

                // 1. Find video_iframe span and trigger its events
                const vf = document.querySelector('.video_iframe');
                if (vf) {
                    logs.push('found video_iframe');
                    vf.click();
                    vf.dispatchEvent(new Event('touchstart', {bubbles: true}));
                    vf.dispatchEvent(new Event('touchend', {bubbles: true}));
                    // Trigger its parent
                    let p = vf.parentElement;
                    while (p && p !== document.body) {
                        p.click();
                        p = p.parentElement;
                    }
                }

                // 2. Find any video element
                const videos = document.querySelectorAll('video');
                logs.push('videos: ' + videos.length);
                videos.forEach(v => {
                    v.play().catch(() => {});
                    v.load();
                });

                // 3. Try to open video player page via JS
                if (vf) {
                    const ds = vf.getAttribute('data-src') || vf.getAttribute('data-url');
                    if (ds) {
                        logs.push('player url: ' + ds.substring(0, 50));
                        const a = document.createElement('a');
                        a.href = ds;
                        a.target = '_blank';
                        a.click();
                    }
                }

                // 4. Find and click all clickable elements near the video
                if (vf) {
                    const rect = vf.getBoundingClientRect();
                    const cx = rect.left + rect.width / 2;
                    const cy = rect.top + rect.height / 2;
                    const el = document.elementFromPoint(cx, cy);
                    if (el) {
                        logs.push('elementAtCenter: ' + el.tagName + '.' + el.className);
                        el.click();
                        // Also click slightly different positions
                        for (let dx of [-10, 10, -20, 20]) {
                            for (let dy of [-10, 10, -20, 20]) {
                                const e2 = document.elementFromPoint(cx + dx, cy + dy);
                                if (e2 && e2 !== el) {
                                    e2.click();
                                }
                            }
                        }
                    }
                }

                // 5. Check for iframe containing video player
                const iframes = document.querySelectorAll('iframe');
                logs.push('iframes: ' + iframes.length);

                // 6. Check what mpvideo elements exist
                const mpv = document.querySelectorAll('mp-common-videosnap, mpvideo');
                logs.push('mpvideo elements: ' + mpv.length);

                return logs;
            }''')
            print(f'  Actions: {result}', flush=True)

            await asyncio.sleep(45)

            # Check if any video src appeared in the page
            new_videos = await page.evaluate('''() => {
                const vs = document.querySelectorAll('video');
                let urls = [];
                vs.forEach(v => urls.push(v.src.substring(0, 80)));
                return urls;
            }''')
            print(f'  Video srcs after: {new_videos}', flush=True)

            await page.close()

            if captured:
                vurl, vdata = next(iter(captured.items()))
                vfname = 'video_1.mp4'
                (article_dir / vfname).write_bytes(vdata)
                print(f'  Saved: {vfname} ({len(vdata)//1024}KB)', flush=True)

                html_path = article_dir / 'index.html'
                html = html_path.read_text(encoding='utf-8')
                html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"',
                              f'src="{vfname}"', html)
                html_path.write_text(html, encoding='utf-8')
                print(f'  HTML updated', flush=True)
            else:
                print(f'  FAILED', flush=True)

            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
