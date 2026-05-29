"""Interactive video download: user manually plays video in browser."""
import asyncio, re, json
from pathlib import Path
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')
TARGETS = [
    ('2021-05-11_欢迎宁校长莅临指导！', 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'),
    ('2021-04-23_RoboMaster2021赛事简介', 'https://mp.weixin.qq.com/s/FBw03JxseIz9fcoU1nqx3Q'),
]

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
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

            html = html_path.read_text(encoding='utf-8')
            soup = BeautifulSoup(html, 'lxml')
            player_url = None
            for vf in soup.find_all('span', class_='video_iframe'):
                ds = vf.get('data-src', '')
                if ds and 'readtemplate' in ds:
                    player_url = ds
                    break

            if not player_url:
                print('  No player URL', flush=True)
                continue

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
            print(f'  Opening article, scroll down and click video to play...')
            await page.goto(article_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            # Scroll down
            th = await page.evaluate('document.body.scrollHeight')
            for pos in range(0, th + 300, 300):
                await page.evaluate(f'window.scrollTo(0, {pos})')
                await asyncio.sleep(0.1)

            print(f'  Browser open - click video to play! Waiting 60s...')
            await asyncio.sleep(60)
            await page.close()

            if captured:
                vurl, vdata = next(iter(captured.items()))
                vfname = 'video_1.mp4'
                (article_dir / vfname).write_bytes(vdata)
                print(f'  Saved: {vfname} ({len(vdata)//1024}KB)')

                html = html_path.read_text(encoding='utf-8')
                html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"',
                              f'src="{vfname}"', html)
                html_path.write_text(html, encoding='utf-8')
                print(f'  HTML updated, remote={"mpvideo.qpic.cn" in html}')
            else:
                print(f'  No video captured in 60s')

            await asyncio.sleep(2)

        await browser.close()
        print('\n=== DONE ===')
        print('Now run: python check_videos.py')

asyncio.run(main())
