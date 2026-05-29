"""Re-download video for article 4 and fix video height."""
import asyncio, re, json, time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

BASE = Path('../doc/public/wechat/articles')

async def redl_video(dir_name, article_url):
    article_dir = BASE / dir_name
    html_path = article_dir / 'index.html'
    print(f'=== {dir_name[:40]} ===', flush=True)

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
        await page.goto(article_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        th = await page.evaluate('document.body.scrollHeight')
        for pos in range(0, th + 300, 300):
            await page.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.1)
        await asyncio.sleep(3)

        fresh_info = await page.evaluate('''() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return {src: v.src, duration: v.duration};
        }''')
        print(f'  Fresh URL: {fresh_info["src"][:100]}...', flush=True)
        print(f'  Duration: {fresh_info["duration"]:.1f}s', flush=True)

        print(f'  Fetching...', flush=True)
        start = time.time()
        try:
            result = await page.evaluate("""async (url) => {
                const r = await fetch(url);
                if (!r.ok) return {status: r.status};
                const buf = await r.arrayBuffer();
                return {status: r.status, size: buf.byteLength, data: Array.from(new Uint8Array(buf))};
            }""", fresh_info['src'])
            elapsed = time.time() - start
            print(f'  status={result["status"]} size={result["size"]} time={elapsed:.1f}s', flush=True)

            if result.get('data') and result['size'] > 100000:
                data = bytes(result['data'])
                (article_dir / 'video_1.mp4').write_bytes(data)
                print(f'  Saved: {len(data)//1024}KB', flush=True)
            else:
                print(f'  Failed', flush=True)
        except Exception as e:
            print(f'  Error: {e}', flush=True)

        await page.close()
        await browser.close()

# Article 4
asyncio.run(redl_video('2020-12-31_2020年终总结', 'https://mp.weixin.qq.com/s/DygKuBiP7yaIOt6DK3WI2g'))
