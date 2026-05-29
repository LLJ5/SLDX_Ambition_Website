"""Download videos by getting fresh CDN URL from page, then fetch."""
import asyncio, re, json, time
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

            page = await ctx.new_page()
            await page.goto(article_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            # Scroll for lazy load
            th = await page.evaluate('document.body.scrollHeight')
            for pos in range(0, th + 300, 300):
                await page.evaluate(f'window.scrollTo(0, {pos})')
                await asyncio.sleep(0.1)
            await asyncio.sleep(3)

            # Get fresh video CDN URL from the page (WeChat JS creates it)
            fresh_info = await page.evaluate('''() => {
                const v = document.querySelector('video');
                if (!v) return null;
                return {
                    src: v.src,
                    duration: v.duration,
                    readyState: v.readyState,
                };
            }''')
            print(f'  Fresh video: {fresh_info}', flush=True)

            if not fresh_info or not fresh_info['src']:
                print('  No video element on page', flush=True)
                await page.close()
                continue

            fresh_url = fresh_info['src']
            print(f'  Fetching from page context...', flush=True)

            # Fetch the full video from within the page context (proper cookies/referer)
            start = time.time()
            try:
                result = await page.evaluate("""async (url) => {
                    const r = await fetch(url);
                    if (!r.ok) return {status: r.status};
                    const buf = await r.arrayBuffer();
                    return {status: r.status, size: buf.byteLength, data: Array.from(new Uint8Array(buf))};
                }""", fresh_url)
                elapsed = time.time() - start
                print(f'  Fetch result: status={result.get("status")}, size={result.get("size", 0)}, time={elapsed:.1f}s', flush=True)

                if result.get('data') and result['size'] > 100000:
                    data = bytes(result['data'])
                    vfname = 'video_1.mp4'
                    (article_dir / vfname).write_bytes(data)
                    print(f'  Saved: {vfname} ({len(data)//1024}KB)', flush=True)

                    html = html_path.read_text(encoding='utf-8')
                    html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"',
                                  f'src="{vfname}"', html)
                    html_path.write_text(html, encoding='utf-8')
                    print(f'  HTML updated', flush=True)
                else:
                    print(f'  Fetch returned too little data', flush=True)
            except Exception as e:
                print(f'  Fetch error: {type(e).__name__}: {e}', flush=True)

            await page.close()
            await asyncio.sleep(2)

        await browser.close()

asyncio.run(main())
