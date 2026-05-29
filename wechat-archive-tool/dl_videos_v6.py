"""Download videos by clicking play on player page."""
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
                            print(f'  Captured: {len(body)//1024}KB from {url[:60]}', flush=True)
                    except:
                        pass

            page = await ctx.new_page()
            page.on('response', hdl)

            print(f'  Opening player: {player_url[:80]}...', flush=True)
            try:
                await page.goto(player_url, wait_until='load', timeout=30000)
                await asyncio.sleep(3)

                # Click play button - try multiple selectors
                clicked = await page.evaluate('''() => {
                    // Try WeChat video player play button
                    const selectors = [
                        '.txp_btn_play', '#txp_btn_play',
                        '.video_player_play', '#js_video_player_play',
                        'video', '.mpvideo_wrp video',
                        '.txp_video_container video',
                        '[class*="play"]', '[id*="play"]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            if (el.tagName === 'VIDEO') {
                                el.play();
                                return 'video.play()';
                            }
                            el.click();
                            return 'clicked ' + sel;
                        }
                    }
                    // Try clicking center of page
                    document.body.click();
                    return 'body click';
                }''')
                print(f'  Click result: {clicked}', flush=True)
                await asyncio.sleep(5)

                # Try clicking again after a short wait
                await page.evaluate('''() => {
                    const v = document.querySelector('video');
                    if (v) { v.play(); v.muted = false; }
                    const btns = document.querySelectorAll('[class*="play"], [class*="btn"]');
                    btns.forEach(b => b.click());
                }''')
                print(f'  Waiting 25s for video...', flush=True)
                await asyncio.sleep(25)

            except Exception as e:
                print(f'  Error: {type(e).__name__}: {e}', flush=True)
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
                print(f'  HTML updated, remote={"mpvideo.qpic.cn" in html}', flush=True)
            else:
                print(f'  FAILED', flush=True)

            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
