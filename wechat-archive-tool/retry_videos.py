"""
Retry video download for articles with video_iframe - multiple attempts per article.
"""
import asyncio, re, json, random, time
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
COOKIES = Path(r'D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json')
TARGETS = ['2021-05-11', '2021-04-23', '2020-12-31', '2020-12-25']
RETRIES = 3

UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/129.0.0.0 Safari/537.36',
]

def detect_ext(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:6] in (b'GIF89a', b'GIF87a'): return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP': return 'webp'
    return 'jpg'

async def try_download(target, article_dir, wechat_url, attempt):
    """Try to download videos. Returns (success_count, video_data_list)"""
    captured = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=[f'--window-size={random.randint(1024,1920)},{random.randint(768,1080)}'])
        ctx = await browser.new_context(
            user_agent=random.choice(UA_POOL),
            viewport={'width': random.randint(1024, 1920), 'height': random.randint(768, 1080)}
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
            if 'video' in ct or 'mpvideo.qpic.cn' in u:
                try:
                    body = await response.body()
                    if body and len(body) > 50000:
                        captured[u] = body
                except: pass
        page.on('response', hdl)
        
        # Navigate to article
        await page.goto(wechat_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)
        
        # Scroll multiple times
        for _ in range(3):
            th = await page.evaluate('document.body.scrollHeight')
            for pos in range(0, th + 200, 200):
                await page.evaluate(f'window.scrollTo(0, {pos})')
                await asyncio.sleep(0.1)
            await asyncio.sleep(2)
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(1)
        
        # Get video_iframe data-src URLs
        vf_urls = await page.evaluate("""() => {
            const urls = [];
            document.querySelectorAll('.video_iframe').forEach(v => {
                if (v.dataset.src) urls.push(v.dataset.src);
            });
            return urls;
        }""")
        
        # Open each player page
        for ds_url in vf_urls:
            if not ds_url: continue
            vp = await ctx.new_page()
            try:
                await vp.goto(ds_url, wait_until='networkidle', timeout=30000)
                await asyncio.sleep(8)
                # Try clicking play
                try:
                    await vp.click('video', timeout=3000)
                    await asyncio.sleep(5)
                except: pass
                try:
                    await vp.evaluate('document.querySelector("video")?.play()')
                    await asyncio.sleep(5)
                except: pass
            except: pass
            await vp.close()
        
        await page.close()
        await ctx.close()
        await browser.close()
    
    return captured

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
        
        print(f'\n=== {ad.name[:50]} ===')
        
        all_captured = {}
        for attempt in range(1, RETRIES + 1):
            print(f'  Attempt {attempt}/{RETRIES}...', end=' ')
            captured = await try_download(target, ad, url, attempt)
            all_captured.update(captured)
            print(f'{len(captured)} captured')
            if captured:
                break
            time.sleep(3)
        
        if not all_captured:
            print(f'  FAILED after {RETRIES} attempts')
            continue
        
        print(f'  Total captured: {len(all_captured)}')
        
        # Save videos
        existing = set(f.name for f in ad.glob('video_*.mp4'))
        video_files = []
        for j, (vurl, data) in enumerate(sorted(all_captured.items())):
            if data and len(data) > 50000:
                fname = f'video_retry_{j+1}.mp4'
                (ad / fname).write_bytes(data)
                video_files.append((vurl, fname, len(data)))
                print(f'    Saved: {fname} ({len(data)//1024}KB)')
        
        if video_files:
            # Replace video_iframe in HTML
            vfs = soup.find_all('span', class_='video_iframe')
            for i, vf in enumerate(vfs):
                if i < len(video_files):
                    tag = soup.new_tag('video')
                    tag['src'] = video_files[i][1]
                    tag['controls'] = ''
                    tag['style'] = 'max-width:100%;width:100%'
                    vf.replace_with(tag)
            
            # Remove any orphaned video tags
            for v in soup.find_all('video'):
                src = v.get('src', '')
                if src and not (ad / src).exists() and not src.startswith('video_retry_'):
                    v.decompose()
            
            result = str(soup).replace('&amp;', '&')
            (ad/'index.html').write_text(result, 'utf-8')
            print(f'  HTML updated: {len(video_files)} videos')

asyncio.run(main())
