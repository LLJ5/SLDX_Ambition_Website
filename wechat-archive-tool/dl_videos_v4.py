"""Download videos by navigating to video player page with auto=1."""
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

            # Read video_iframe data-src from HTML
            html = html_path.read_text(encoding='utf-8')
            soup = BeautifulSoup(html, 'lxml')
            player_url = None
            for vf in soup.find_all('span', class_='video_iframe'):
                ds = vf.get('data-src', '')
                if ds and 'readtemplate' in ds:
                    player_url = ds.replace('auto=0', 'auto=1')
                    break

            # Also get direct video CDN URL
            video_src = None
            for v in soup.find_all('video'):
                src = v.get('src', '')
                if 'mpvideo.qpic.cn' in src:
                    video_src = src
                    break

            if not player_url and not video_src:
                print('  No video URLs found', flush=True)
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

            # Strategy 1: Navigate to video player page with auto=1
            page = await ctx.new_page()
            page.on('response', hdl)
            if player_url:
                print(f'  Player: {player_url[:80]}...', flush=True)
                try:
                    await page.goto(player_url, wait_until='load', timeout=25000)
                    print(f'  Loaded, waiting 15s...', flush=True)
                    await asyncio.sleep(15)
                except Exception as e:
                    print(f'  Player page error: {e}', flush=True)
            await page.close()

            # Strategy 2: If no video, try fetching from article page context
            if not captured:
                page2 = await ctx.new_page()
                print(f'  Loading article for fetch...', flush=True)
                try:
                    await page2.goto(article_url, wait_until='domcontentloaded', timeout=20000)
                    await asyncio.sleep(3)

                    # Try to find and play video element
                    await page2.evaluate('''() => {
                        const v = document.querySelector('video');
                        if (v) v.play();
                        const vf = document.querySelector('.video_iframe');
                        if (vf) vf.click();
                    }''')
                    await asyncio.sleep(10)

                    # Fetch from video CDN
                    if video_src and not captured:
                        print(f'  Fetching CDN URL...', flush=True)
                        try:
                            result = await page2.evaluate("""async (url) => {
                                const r = await fetch(url);
                                if (!r.ok) return null;
                                const buf = await r.arrayBuffer();
                                return Array.from(new Uint8Array(buf));
                            }""", video_src)
                            if result and len(result) > 100000:
                                captured[video_src] = bytes(result)
                                print(f'  Fetched: {len(result)//1024}KB')
                            else:
                                sz = len(result) if result else 0
                                print(f'  Fetch result: {sz}B', flush=True)
                        except Exception as e:
                            print(f'  Fetch error: {e}', flush=True)
                except Exception as e:
                    print(f'  Article error: {e}', flush=True)
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
