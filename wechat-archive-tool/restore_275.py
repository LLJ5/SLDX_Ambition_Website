"""Find and re-download the 2.7.5 article that was accidentally deleted."""
import asyncio, json, re, base64, shutil
from pathlib import Path
from bs4 import BeautifulSoup

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36')
        cf = Path(r'D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json')
        if cf.exists(): await ctx.add_cookies(json.loads(cf.read_text()))

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)
        
        # Search MP backend for article
        await page.goto('https://mp.weixin.qq.com/', wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        token = re.search(r'token=(\d+)', page.url).group(1)
        
        api_url = f'https://mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex&begin=0&count=50&type=9&query=2.7.5&token={token}&lang=zh_CN&f=json'
        resp = await page.evaluate(f"async () => {{ const r = await fetch('{api_url}'); return await r.text(); }}")
        data = json.loads(resp)
        
        article_url = None
        article_title = None
        if 'app_msg_list' in data:
            for art in data['app_msg_list']:
                title = art.get('title', '')
                link = art.get('link', '')
                if '2.7.5' in title:
                    article_url = link + '#rd'
                    article_title = title
                    print(f'Found: {title}')
                    print(f'URL: {link}')
                    break
        
        if not article_url:
            print('Article not found')
            await browser.close()
            return
        
        # Download
        captured = {}
        async def hdl(r):
            u = r.url
            if r.status == 200 and 'mmbiz.qpic.cn' in u:
                try:
                    body = await r.body()
                    if len(body) > 200: captured[u] = body; captured[u.split('?')[0]] = body
                except: pass
        page.on('response', hdl)
        
        await page.goto(article_url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)
        for i in range(20):
            await page.evaluate(f'window.scrollTo(0, {i * 600})')
            await asyncio.sleep(0.5)
        await asyncio.sleep(5)
        
        live = await page.content()
        soup = BeautifulSoup(live, 'lxml')
        js = soup.find(id='js_content')
        
        if not js:
            print('No js_content')
            await browser.close()
            return
        
        print(f'Content: {len(js.get_text(strip=True))} chars, {len(js.find_all("img"))} imgs, {len(captured)} captured')
        
        # Template
        td = None
        for x in BASE.iterdir():
            if x.is_dir() and x.name.startswith('2023-12-13_'): td = x; break
        template_html = (td / 'index.html').read_text(encoding='utf-8')
        
        # Create directory (NOT deleting anything)
        title_tag = soup.find('title')
        title = title_tag.string if title_tag else '2.7.5_根本放不下'
        import re as re2
        safe = re2.sub(r'[<>:"/\\|?*\s]', '_', title.strip())[:50]
        
        # Use existing dir if available
        dir_name = None
        for d in BASE.iterdir():
            if '2025-03-24' in d.name and '2.7.5' in d.name:
                dir_name = d.name
                break
        if not dir_name:
            dir_name = f'2025-03-24_{safe}'
        
        article_dir = BASE / dir_name
        article_dir.mkdir(parents=True, exist_ok=True)
        
        all_urls = set()
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and 'mmbiz.qpic.cn' in val and not val.startswith('data:'):
                    if val.startswith('//'): val = 'https:' + val
                    all_urls.add(val)
        
        url_to_local = {}
        idx = 1
        for url in sorted(all_urls):
            data = captured.get(url) or captured.get(url.split('?')[0])
            if data and len(data) > 200:
                ext = 'jpg'
                if data[:4] == b'\x89PNG': ext = 'png'
                elif data[:3] == b'GIF': ext = 'gif'
                elif data[:4] == b'RIFF': ext = 'webp'
                local = f'img_{idx}.{ext}'
                (article_dir / local).write_bytes(data)
                url_to_local[url] = local; idx += 1
        
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and 'mmbiz.qpic.cn' in val:
                    if val.startswith('//'): val = 'https:' + val
                    for cdn, local in url_to_local.items():
                        if val in cdn or cdn in val: img[attr] = local; break
        
        new_soup = BeautifulSoup(template_html, 'lxml')
        for meta, attr in [('og:title','property'),('og:url','property'),('og:image','property')]:
            src = soup.find('meta', attrs={attr: meta})
            dst = new_soup.find('meta', attrs={attr: meta})
            if src and dst and src.get('content'): dst['content'] = src['content']
        
        ti = new_soup.find('title'); og = soup.find('meta', property='og:title')
        if ti and og: ti.string = og.get('content','')
        
        nj = new_soup.find(id='js_content')
        if nj: nj.clear(); [nj.append(c) for c in js.contents]
        
        h1 = soup.find(id='activity-name'); nh = new_soup.find(id='activity-name')
        if h1 and nh:
            nh.clear(); sp = new_soup.new_tag('span'); sp['class'] = 'js_title_inner'
            sp.string = h1.get_text(strip=True); nh.append(sp)
        
        for eid in ['js_author_name_text','publish_time']:
            e1 = soup.find(id=eid); e2 = new_soup.find(id=eid)
            if e1 and e2: e2.string = e1.get_text(strip=True)
        
        for img in new_soup.find_all('img'):
            cl = img.get('class', []); cl = cl.split() if isinstance(cl,str) else cl
            nc = [c for c in cl if c not in ('js_img_placeholder','wx_img_placeholder')]
            if nc: img['class'] = ' '.join(nc)
            elif img.has_attr('class'): del img['class']
        
        result = str(new_soup)
        result = result.replace('大冲在思考','沈理电协')
        result = re2.sub(r'#imgIndex=\d+','',result)
        result = result.replace('&amp;','&')
        (article_dir / 'index.html').write_text(result, encoding='utf-8')
        
        remote = len(re2.findall(r'mmbiz\.qpic\.cn', result))
        print(f'Done: {idx-1} imgs, {remote} remote, {len(result)}B')
        
        await browser.close()

asyncio.run(main())
