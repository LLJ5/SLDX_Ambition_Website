"""
Open article pages for manual video loading. User triggers videos, script captures them.
"""
import asyncio, re, json, random
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
COOKIES = Path(r'D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json')
TARGETS = ['2021-05-11', '2021-04-23', '2020-12-31', '2020-12-25']

async def main():
    for target in TARGETS:
        ads = [x for x in BASE.iterdir() if x.is_dir() and x.name.startswith(target)]
        if not ads: continue
        ad = ads[0]
        h = (ad/'index.html').read_text('utf-8', errors='ignore')
        soup = BeautifulSoup(h, 'lxml')
        og = soup.find('meta', property='og:url')
        url = og['content'] if og else None
        if not url: continue
        
        print(f'\n=== Opening: {ad.name[:50]} ===')
        print(f'URL: {url}')
        
        captured = {}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=[f'--window-size=1400,900'])
            ctx = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1400, 'height': 900}
            )
            if COOKIES.exists():
                try: await ctx.add_cookies(json.loads(COOKIES.read_text()))
                except: pass
            
            page = await ctx.new_page()
            stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
            await stealth.apply_stealth_async(page)
            
            async def hdl(response):
                u = response.url
                ct = response.headers.get('content-type', '')
                if ('video' in ct or 'mpvideo.qpic.cn' in u) and 'mp4' in u.lower():
                    try:
                        body = await response.body()
                        if body and len(body) > 50000:
                            captured[u] = body
                            print(f'  >>> CAPTURED VIDEO: {len(body)}B')
                    except: pass
            page.on('response', hdl)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            input(f'\n  手动滚动页面、点击视频播放。完成后按回车继续...')
            
            print(f'  捕获到 {len(captured)} 个视频')
            
            if captured:
                # Save videos
                existing = set(f.name for f in ad.glob('video_*.mp4'))
                video_files = []
                for j, (vurl, data) in enumerate(sorted(captured.items())):
                    if data and len(data) > 50000:
                        fname = f'video_{j+1}.mp4'
                        (ad / fname).write_bytes(data)
                        video_files.append((vurl, fname, len(data)))
                        print(f'    Saved: {fname} ({len(data)//1024}KB)')
                
                # Update HTML
                vfs = soup.find_all('span', class_='video_iframe')
                for i, vf in enumerate(vfs):
                    if i < len(video_files):
                        tag = soup.new_tag('video')
                        tag['src'] = video_files[i][1]
                        tag['controls'] = ''
                        tag['style'] = 'max-width:100%;width:100%'
                        vf.replace_with(tag)
                
                result = str(soup).replace('&amp;', '&')
                (ad/'index.html').write_text(result, 'utf-8')
                print(f'    HTML updated')
            
            await page.close()
            await ctx.close()
            await browser.close()

asyncio.run(main())
