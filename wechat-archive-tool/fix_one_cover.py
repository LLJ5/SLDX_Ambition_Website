import asyncio, re, random
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
TARGETS = ['2016-04-23', '2016-12-01', '2020-12-27']

def detect_ext(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:6] in (b'GIF89a', b'GIF87a'): return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    return 'jpg'

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900}
        )
        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        for target in TARGETS:
            ads = [x for x in BASE.iterdir() if x.is_dir() and x.name.startswith(target)]
            if not ads: continue
            ad = ads[0]
            h = (ad/'index.html').read_text('utf-8', errors='ignore')
            soup = BeautifulSoup(h, 'lxml')
            og_url_tag = soup.find('meta', property='og:url')
            url = og_url_tag.get('content') if og_url_tag else None
            if not url: continue
            
            print(f'{ad.name[:50]}')
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)
            live = await page.content()
            live_soup = BeautifulSoup(live, 'lxml')
            og_img = live_soup.find('meta', property='og:image')
            cover_url = og_img.get('content') if og_img else None
            
            if cover_url:
                cover_url = cover_url.replace('http://', 'https://')
                result = await page.evaluate("""async (u) => {
                    try { const r = await fetch(u);
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", cover_url)
                if result and len(result) > 500:
                    data = bytes(result)
                    ext = detect_ext(data)
                    cp = ad / f'cover.{ext}'
                    cp.write_bytes(data)
                    html = (ad/'index.html').read_text('utf-8')
                    html = re.sub(r'content="[^"]*"\s+property="og:image"', f'content="cover.{ext}" property="og:image"', html)
                    html = re.sub(r'content="[^"]*"\s+property="twitter:image"', f'content="cover.{ext}" property="twitter:image"', html)
                    (ad/'index.html').write_text(html, 'utf-8')
                    print(f'  -> cover.{ext} ({len(data)}B)')
                else:
                    print(f'  -> FAILED: {len(result) if result else 0}B')
            else:
                print(f'  -> no og:image on live page')

        await page.close()
        await ctx.close()
        await browser.close()

asyncio.run(main())
