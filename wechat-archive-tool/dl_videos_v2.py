"""Download videos for articles 1-3 via video player page interception."""
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

            # Read HTML to get video src URL
            html = (html_path).read_text(encoding='utf-8')
            soup = BeautifulSoup(html, 'lxml')
            video_src = None
            for v in soup.find_all('video'):
                src = v.get('src', '')
                if 'mpvideo.qpic.cn' in src:
                    video_src = src
                    break

            # Also get video_iframe data-src (player page URL)
            video_player_url = None
            for vf in soup.find_all('span', class_='video_iframe'):
                ds = vf.get('data-src', '')
                if ds:
                    video_player_url = ds
                    break

            if not video_src and not video_player_url:
                print('  No video URL found, skipping')
                continue

            print(f'  Player URL: {video_player_url[:80] if video_player_url else "N/A"}...')
            print(f'  Video CDN: {video_src[:80] if video_src else "N/A"}...')

            # Open article page first to get cookies
            page = await ctx.new_page()
            try:
                await page.goto(article_url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)
            except:
                pass
            await page.close()

            # Now open video player page and capture video response
            captured = {}
            async def hdl(response):
                url = response.url
                ct = response.headers.get('content-type', '')
                if 'video' in ct or 'mpvideo.qpic.cn' in url:
                    if url not in captured:
                        try:
                            body = await response.body()
                            if body and len(body) > 100000:
                                captured[url] = body
                                print(f'    Captured: {len(body)//1024}KB from {url[:60]}')
                        except:
                            pass

            if video_player_url:
                vp = await ctx.new_page()
                vp.on('response', hdl)
                try:
                    print('  Opening video player page...')
                    await vp.goto(video_player_url, wait_until='load', timeout=30000)
                    print('  Waiting for video to load (15s)...')
                    await asyncio.sleep(15)
                except Exception as e:
                    print(f'  Player page error: {e}')
                await vp.close()

            # If not captured, try fetching from CDN directly via article page
            if not captured and video_src:
                print('  Trying direct fetch from article page...')
                page2 = await ctx.new_page()
                await page2.goto(article_url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)
                try:
                    result = await page2.evaluate("""async (url) => {
                        try {
                            const r = await fetch(url);
                            if (!r.ok) return null;
                            const buf = await r.arrayBuffer();
                            return Array.from(new Uint8Array(buf));
                        } catch(e) { return null; }
                    }""", video_src)
                    if result and len(result) > 100000:
                        captured[video_src] = bytes(result)
                        print(f'    Fetched: {len(result)//1024}KB')
                    else:
                        sz = len(result) if result else 0
                        print(f'    Fetch failed: {sz}B')
                except Exception as e:
                    print(f'    Fetch error: {e}')
                await page2.close()

            if captured:
                # Save first captured video
                vurl, vdata = next(iter(captured.items()))
                vfname = 'video_1.mp4'
                (article_dir / vfname).write_bytes(vdata)
                print(f'    Saved: {vfname} ({len(vdata)//1024}KB)')

                # Update HTML
                html = (html_path).read_text(encoding='utf-8')
                html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"',
                              f'src="{vfname}"', html)
                html_path.write_text(html, encoding='utf-8')
                print(f'    HTML updated, remote={"mpvideo.qpic.cn" in html}')
            else:
                print('  FAILED to capture video')

            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
