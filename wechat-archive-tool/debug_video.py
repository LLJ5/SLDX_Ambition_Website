import asyncio, re, json, random
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

COOKIES = Path(r'D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json')
AD = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

async def main():
    # Find the article directory
    ads = [x for x in AD.iterdir() if x.is_dir() and '2023-03-31' in x.name and '平衡' in x.name]
    if not ads: ads = [x for x in AD.iterdir() if x.is_dir() and x.name.startswith('2023-03-31')]
    if not ads: return
    ad = ads[0]
    h = (ad/'index.html').read_text('utf-8', errors='ignore')
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(h, 'lxml')
    og_url_tag = soup.find('meta', property='og:url')
    article_url = og_url_tag['content'] if og_url_tag else None
    print(f'Article URL: {article_url}')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
        )
        # Try loading cookies
        if COOKIES.exists():
            try: await ctx.add_cookies(json.loads(COOKIES.read_text()))
            except: pass
        
        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)
        
        captured = {}
        async def hdl(response):
            u = response.url
            if 'mpvideo.qpic.cn' in u or 'video.qq.com' in u:
                try:
                    body = await response.body()
                    if body and len(body) > 50000:
                        captured[u] = body
                        print(f'  CAPTURED: {len(body)}B from {u[:100]}')
                except: pass
        page.on('response', hdl)
        
        await page.goto(article_url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)
        
        # Check js_content
        js_check = await page.evaluate('document.getElementById("js_content")?document.getElementById("js_content").innerHTML.length:0')
        print(f'js_content length: {js_check}')
        
        # Scroll
        th = await page.evaluate('document.body.scrollHeight')
        for pos in range(0, th + 300, 300):
            await page.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.2)
        await asyncio.sleep(3)
        
        # Try clicking video iframes
        vfs = await page.evaluate("""() => {
            const spans = document.querySelectorAll('.video_iframe');
            return spans.length;
        }""")
        print(f'video_iframe on page: {vfs}')
        
        # Try clicking each
        for i in range(vfs):
            try:
                await page.evaluate(f"""() => {{
                    const spans = document.querySelectorAll('.video_iframe');
                    if (spans[{i}]) spans[{i}].click();
                }}""")
                await asyncio.sleep(3)
            except: pass
        
        print(f'Total captured: {len(captured)}')
        for u, data in captured.items():
            print(f'  {len(data)}B: {u[:100]}')
        
        await page.close()
        await ctx.close()
        await browser.close()

asyncio.run(main())
