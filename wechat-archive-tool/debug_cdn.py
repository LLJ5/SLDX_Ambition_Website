"""Debug: check what CDN URL and player page return."""
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

        # Article 2 CDN URL
        cdn_url = 'https://mpvideo.qpic.cn/0bf2cuaf2aaaa4am3i42kjqfafodlukqaxia.f10002.mp4'

        page = await ctx.new_page()

        # Navigate article first
        await page.goto('https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g', wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(3)

        # Try fetch from page context
        print('Fetching from article page context...')
        result = await page.evaluate("""async (url) => {
            try {
                const r = await fetch(url, {referrer: 'https://mp.weixin.qq.com/'});
                console.log('Status:', r.status, 'Type:', r.headers.get('content-type'));
                if (!r.ok) return {status: r.status, type: r.headers.get('content-type')};
                const buf = await r.arrayBuffer();
                return {status: r.status, type: r.headers.get('content-type'), size: buf.byteLength};
            } catch(e) { return {error: e.message}; }
        }""", cdn_url)
        print(f'Fetch result: {result}')

        # Also try with specific referer header
        result2 = await page.evaluate("""async (url) => {
            try {
                const r = await fetch(url, {
                    headers: {'Referer': 'https://mp.weixin.qq.com/'},
                    referrer: 'https://mp.weixin.qq.com/',
                    referrerPolicy: 'no-referrer-when-downgrade'
                });
                console.log('Status2:', r.status);
                if (!r.ok) return {status: r.status};
                const buf = await r.arrayBuffer();
                return {status: r.status, type: r.headers.get('content-type'), size: buf.byteLength};
            } catch(e) { return {error: e.message}; }
        }""", cdn_url)
        print(f'Fetch with referer: {result2}')

        await browser.close()

asyncio.run(main())
