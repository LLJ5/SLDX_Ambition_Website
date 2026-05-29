"""Quick test: navigate to WeChat article page."""
import asyncio, json
from pathlib import Path

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
            print('Cookies loaded')
        else:
            print('NO COOKIES FILE')

        page = await ctx.new_page()
        url = 'https://mp.weixin.qq.com/s/Aiev7wTXnex6ZU3CK7zx4g'
        print(f'Navigating to: {url[:60]}...')
        try:
            resp = await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            print(f'Status: {resp.status}')
            title = await page.title()
            print(f'Title: {title}')
            html = await page.content()
            print(f'HTML size: {len(html)}B')
            has_js = 'id="js_content"' in html
            has_captcha = '验证' in html or 'captcha' in html.lower() or '频繁' in html
            print(f'js_content: {has_js}, captcha: {has_captcha}')
        except Exception as e:
            print(f'ERROR: {type(e).__name__}: {e}')

        await browser.close()

asyncio.run(main())
