"""Download videos for articles 2 and 3: navigate to CDN URL directly."""
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

            html = html_path.read_text(encoding='utf-8')
            soup = BeautifulSoup(html, 'lxml')

            # Get video CDN URL from <video> element
            video_src = None
            for v in soup.find_all('video'):
                src = v.get('src', '')
                if 'mpvideo.qpic.cn' in src:
                    video_src = src
                    break

            # Get video player page URL
            player_url = None
            for vf in soup.find_all('span', class_='video_iframe'):
                ds = vf.get('data-src', '')
                if ds and 'readtemplate' in ds:
                    player_url = ds.replace('auto=0', 'auto=1')
                    break

            if not video_src:
                print('  No video CDN URL', flush=True)
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
                            print(f'  Captured: {len(body)//1024}KB', flush=True)
                    except:
                        pass

            # Step 1: Navigate article page first (for referer/cookies)
            page = await ctx.new_page()
            page.on('response', hdl)
            try:
                print(f'  Loading article...', flush=True)
                await page.goto(article_url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(2)

                # Step 2: Navigate directly to video CDN URL
                print(f'  Navigating to CDN URL...', flush=True)
                print(f'  {video_src[:100]}...', flush=True)
                try:
                    await page.goto(video_src, wait_until='load', timeout=30000)
                    print(f'  CDN response loaded', flush=True)
                    await asyncio.sleep(5)
                except Exception as e:
                    print(f'  CDN nav error: {type(e).__name__}', flush=True)
            except Exception as e:
                print(f'  Article error: {type(e).__name__}', flush=True)
            await page.close()

            # Step 3: If not captured, try player page
            if not captured and player_url:
                page2 = await ctx.new_page()
                page2.on('response', hdl)
                print(f'  Trying player page...', flush=True)
                try:
                    await page2.goto(player_url, wait_until='load', timeout=25000)
                    print(f'  Player loaded, waiting 15s...', flush=True)
                    await asyncio.sleep(15)
                except Exception as e:
                    print(f'  Player error: {type(e).__name__}', flush=True)
                await page2.close()

            if captured:
                vurl, vdata = next(iter(captured.items()))
                vfname = 'video_1.mp4'
                (article_dir / vfname).write_bytes(vdata)
                print(f'  Saved: {vfname} ({len(vdata)//1024}KB)', flush=True)

                html = html_path.read_text(encoding='utf-8')
                html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"',
                              f'src="{vfname}"', html)
                html_path.write_text(html, encoding='utf-8')
                print(f'  HTML updated, remote={"mpvideo.qpic.cn" in html}', flush=True)
            else:
                print(f'  FAILED', flush=True)

            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
