"""Download videos by triggering playback on article page."""
import asyncio, re, json
from pathlib import Path
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')
TARGETS = [
    ('2022-03-08_戴最可爱的发绳，造最猛的机器人！', 'https://mp.weixin.qq.com/s/cx6wRRdnZyC-f8j59tVrCQ'),
    ('2021-05-11_欢迎宁校长莅临指导！', 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'),
    ('2021-04-23_RoboMaster2021赛事简介', 'https://mp.weixin.qq.com/s/FBw03JxseIz9fcoU1nqx3Q'),
]

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

        for dir_name, article_url in TARGETS:
            article_dir = BASE / dir_name
            html_path = article_dir / 'index.html'
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
            page.on('response', hdl)

            try:
                print(f'  Loading article...', flush=True)
                await page.goto(article_url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)

                # Scroll to bottom to trigger lazy loading
                th = await page.evaluate('document.body.scrollHeight')
                for pos in range(0, th + 300, 300):
                    await page.evaluate(f'window.scrollTo(0, {pos})')
                    await asyncio.sleep(0.1)

                await asyncio.sleep(2)

                # Try to click video iframe to trigger playback
                clicked = await page.evaluate('''() => {
                    const vf = document.querySelector('.video_iframe');
                    if (vf) { vf.click(); return true; }
                    // Try video element
                    const v = document.querySelector('video');
                    if (v) { v.play(); return true; }
                    return false;
                }''')
                print(f'  Clicked video: {clicked}', flush=True)

                if clicked:
                    print(f'  Waiting for video load (20s)...', flush=True)
                    await asyncio.sleep(20)
                else:
                    print(f'  No video element found to click', flush=True)

            except Exception as e:
                print(f'  Error: {e}', flush=True)
            finally:
                await page.close()

            if captured:
                vurl, vdata = next(iter(captured.items()))
                vfname = 'video_1.mp4'
                (article_dir / vfname).write_bytes(vdata)
                print(f'  Saved: {vfname} ({len(vdata)//1024}KB)', flush=True)

                html = html_path.read_text(encoding='utf-8')
                html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"',
                              f'src="{vfname}"', html)
                html_path.write_text(html, encoding='utf-8')
                r = 'mpvideo.qpic.cn' in html
                print(f'  HTML updated, remote={r}', flush=True)
            else:
                print(f'  FAILED: no video captured', flush=True)

            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
