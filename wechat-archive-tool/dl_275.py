"""Re-download 2.7.5 article using downloader's standard pipeline, no template replacement."""
import asyncio, json, re, base64
from pathlib import Path
from bs4 import BeautifulSoup

URL = 'http://mp.weixin.qq.com/s?__biz=MzAwMDM4NTYzMQ==&mid=2693317955&idx=2&sn=7a968c5f73a635962fa41d11d04c60a7&chksm=bf95d27388e25b65536055016f4b8d50ca5793354e3112e043c4d5e132f0d68c338246173bce#rd'

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

async def main():
    import sys
    sys.path.insert(0, r'D:\SLDX_Ambition_Website\wechat-archive-tool')
    from src.downloader import ArticleDownloader
    from src.config import Config
    from playwright_stealth import Stealth
    
    # Find article dir - should already exist
    article_dir = None
    for d in BASE.iterdir():
        if '2025-03-24' in d.name and '2.7.5' in d.name:
            article_dir = d
            break
    
    config = Config()
    config._data['output_dir'] = r'D:\SLDX_Ambition_Website\doc\public\wechat'
    config._data['download_videos'] = False
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36')
        cf = Path(r'D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json')
        if cf.exists(): await ctx.add_cookies(json.loads(cf.read_text()))
        
        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)
        
        dl = ArticleDownloader(page, config)
        
        # Capture images via network interception
        captured = {}
        async def hdl(r):
            u = r.url
            if r.status == 200 and 'mmbiz.qpic.cn' in u:
                try:
                    body = await r.body()
                    if len(body) > 200: captured[u] = body; captured[u.split('?')[0]] = body
                except: pass
        page.on('response', hdl)
        
        await page.goto(URL, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)
        for i in range(15):
            await page.evaluate(f'window.scrollTo(0, {i * 600})')
            await asyncio.sleep(0.3)
        await asyncio.sleep(3)
        
        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')
        
        # Use downloader pipeline (but keep original HTML structure)
        dl._fix_image_urls(soup)
        dl._clean_html(soup)
        
        # Replace text
        html_str = str(soup).replace('大冲在思考', '沈理电协')
        
        # Download images by matching CDN URLs to captured data
        import aiohttp
        
        cookies_dict = {}
        try:
            for c in await page.context.cookies():
                domain = c.get('domain', '') or ''
                if any(d in domain for d in ['weixin', 'qq']):
                    cookies_dict[c['name']] = c['value']
        except: pass
        
        # Also download via aiohttp as fallback
        async with aiohttp.ClientSession(
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': URL},
            cookies=cookies_dict,
        ) as session:
            dl.session = session
            await dl._download_body_images(soup, str(article_dir))
        
        # Also update with browser-captured images
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and 'mmbiz.qpic.cn' in src:
                if src.startswith('//'): src = 'https:' + src
                data = captured.get(src) or captured.get(src.split('?')[0])
                if data and len(data) > 200:
                    # Replace with captured version
                    ext = 'jpg'
                    if data[:4] == b'\x89PNG': ext = 'png'
                    elif data[:3] == b'GIF': ext = 'gif'
                    elif data[:4] == b'RIFF': ext = 'webp'
                    # Find matching existing file or create new
                    found = False
                    for f in article_dir.glob('img_*'):
                        if f.read_bytes() == data: found = True; break
                    if not found:
                        n = len(list(article_dir.glob('img_*'))) + 1
                        local = f'img_{n}.{ext}'
                        (article_dir / local).write_bytes(data)
                        img['src'] = local
        
        # Update title
        title_tag = soup.find('title')
        og_title = soup.find('meta', property='og:title')
        if not title_tag and og_title:
            head = soup.find('head')
            if head:
                t = soup.new_tag('title')
                t.string = og_title.get('content', '')
                head.append(t)
        
        # Save directly (NO template replacement)
        result = str(soup)
        result = result.replace('大冲在思考', '沈理电协')
        result = result.replace('&amp;', '&')
        result = re.sub(r'#imgIndex=\d+', '', result)
        
        (article_dir / 'index.html').write_text(result, encoding='utf-8')
        
        remote = len(re.findall(r'mmbiz\.qpic\.cn', result))
        print(f'Done: {len(list(article_dir.glob("img_*")))} imgs, {remote} remote, {len(result)}B')
        
        # Clean remaining remotes
        if remote > 0:
            html = (article_dir / 'index.html').read_text(encoding='utf-8')
            remotes = set(re.findall(r'https?://mmbiz\.qpic\.cn/[^"\s]+', html))
            for url in remotes:
                du = await page.evaluate("""async (url) => {
                    try { const r = await fetch(url); if (!r.ok) return null;
                    const b = await r.blob();
                    return new Promise(res => { const fr = new FileReader();
                    fr.onloadend = () => res(fr.result); fr.readAsDataURL(b); });
                    } catch(e) { return null; }
                }""", url)
                if du and 'data:' in du:
                    data = base64.b64decode(du.split(',', 1)[1])
                    ext = 'jpg'
                    if data[:4] == b'\x89PNG': ext = 'png'
                    elif data[:3] == b'GIF': ext = 'gif'
                    n = len(list(article_dir.glob('rem_*'))) + 1
                    local = f'rem_{n}.{ext}'
                    (article_dir / local).write_bytes(data)
                    html = html.replace(url, local)
                    if url.startswith('https:'): html = html.replace('//' + url[8:], local)
            (article_dir / 'index.html').write_text(html, encoding='utf-8')
            print(f'Final remote: {len(re.findall(r"mmbiz\.qpic\.cn", html))}')
        
        await browser.close()

asyncio.run(main())
