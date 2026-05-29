"""Re-download 2.7.5 article with short URL + proper template head."""
import asyncio, json, re, base64, urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

SHORT_URL = 'https://mp.weixin.qq.com/s/5tWwUJKCVuQYr2E_crKrkw'
DIR_MATCH = '2.7.5'
TEMPLATE_MATCH = '冬日畅言'  # appmsg template (standard article type)

BASE = Path('D:/SLDX_Ambition_Website/doc/public/wechat/articles')

def find_dir(pattern):
    for d in BASE.iterdir():
        if d.is_dir() and pattern in d.name:
            return d
    return None

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
        )
        cf = Path('wechat_cookies.json')
        if cf.exists():
            try: await ctx.add_cookies(json.loads(cf.read_text()))
            except: pass

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        # Network interception
        captured = {}
        async def hdl(r):
            u = r.url
            if r.status == 200 and ('mmbiz.qpic.cn' in u or 'mmecoa.qpic.cn' in u):
                try:
                    body = await r.body()
                    if len(body) > 200:
                        captured[u] = body
                        captured[u.split('?')[0]] = body
                except: pass
        page.on('response', hdl)

        print('Loading article (short URL)...')
        await page.goto(SHORT_URL, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)
        for i in range(20):
            await page.evaluate(f'window.scrollTo(0, {i * 600})')
            await asyncio.sleep(0.5)
        await asyncio.sleep(3)

        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')
        js = soup.find(id='js_content')

        if not js or len(str(js)) < 2000:
            print('ERROR: empty js_content')
            await browser.close()
            return

        print(f'Content: {len(str(js))} html chars, {len(js.find_all("img"))} imgs, {len(captured)} captured')

        # Save og:image URL FIRST before anything else
        og_img_tag = soup.find('meta', property='og:image')
        og_img_url = og_img_tag['content'] if og_img_tag and og_img_tag.get('content') else None
        print(f'og:image URL: {og_img_url[:100] if og_img_url else "NOT FOUND"}')

        # Find article directory
        article_dir = find_dir(DIR_MATCH)
        if not article_dir:
            print('ERROR: article dir not found')
            await browser.close()
            return
        print(f'Article dir: {article_dir.name}')

        # Find template
        template_dir = find_dir(TEMPLATE_MATCH)
        if not template_dir:
            for d in sorted(BASE.iterdir(), reverse=True):
                if d.is_dir() and (d / 'index.html').exists():
                    template_dir = d; break
        template_html = (template_dir / 'index.html').read_text('utf-8')
        print(f'Template: {template_dir.name}')

        # Collect all CDN URLs from js_content
        def is_cdn(u):
            return 'mmbiz.qpic.cn' in u or 'mmecoa.qpic.cn' in u

        all_urls = set()
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and is_cdn(val) and not val.startswith('data:'):
                    if val.startswith('//'): val = 'https:' + val
                    all_urls.add(val)

        for tag in js.find_all(style=True):
            st = tag.get('style', '')
            for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
                if is_cdn(m.group(1)):
                    u = m.group(1)
                    if u.startswith('//'): u = 'https:' + u
                    all_urls.add(u)

        for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
            u = tag.get('data-lazy-bgimg', '')
            if is_cdn(u):
                if u.startswith('//'): u = 'https:' + u
                all_urls.add(u)

        print(f'CDN URLs: {len(all_urls)}')

        # Delete old images
        for f in article_dir.glob('img_*'): f.unlink()
        for f in article_dir.glob('rem_*'): f.unlink()

        # Save images
        url_map = {}
        idx = 1
        for url in sorted(all_urls):
            data = captured.get(url) or captured.get(url.split('?')[0])
            if data and len(data) > 200:
                ext = 'jpg'
                if data[:4] == b'\x89PNG': ext = 'png'
                elif data[:3] == b'GIF': ext = 'gif'
                elif data[:4] == b'RIFF' and data[8:12] == b'WEBP': ext = 'webp'
                elif data.startswith(b'<?xml') or data.startswith(b'<svg'): ext = 'svg'
                local = f'img_{idx}.{ext}'
                (article_dir / local).write_bytes(data)
                url_map[url] = local
                idx += 1

        print(f'Saved {len(url_map)} imgs')

        # Replace URLs in js_content
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and is_cdn(val):
                    if val.startswith('//'): val = 'https:' + val
                    for cdn, loc in url_map.items():
                        if val == cdn or val == cdn.split('?')[0]:
                            img[attr] = loc; break
            st = img.get('style', '')
            for cdn, loc in url_map.items():
                if cdn in st: st = st.replace(cdn, loc)
            img['style'] = st

        for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
            bg = tag.get('data-lazy-bgimg', '')
            for cdn, loc in url_map.items():
                if cdn in bg: tag['data-lazy-bgimg'] = loc; break

        # Build new HTML with template head
        new_soup = BeautifulSoup(template_html, 'lxml')

        # Replace metadata from live page
        for meta_name, attr in [('og:title','property'),('og:url','property'),
                                 ('og:image','property'),('og:description','property'),
                                 ('og:article:author','property'),('og:site_name','property'),
                                 ('og:type','property'),
                                 ('twitter:title','property'),('twitter:image','property'),
                                 ('twitter:creator','property'),('twitter:site','property'),
                                 ('twitter:description','property'),
                                 ('description','name'),('author','name')]:
            src = soup.find('meta', attrs={attr: meta_name})
            dst = new_soup.find('meta', attrs={attr: meta_name})
            if src and dst and src.get('content'):
                dst['content'] = src['content']

        # Title
        ti = new_soup.find('title')
        og_ti = soup.find('meta', property='og:title')
        if ti and og_ti and og_ti.get('content'):
            ti.string = og_ti['content']

        # Replace js_content
        nj = new_soup.find(id='js_content')
        if nj:
            nj.clear()
            for c in list(js.contents):
                try: nj.append(c)
                except:
                    cc = BeautifulSoup(str(c), 'lxml').find()
                    if cc: nj.append(cc)

        # H1 title - handle both appmsg (#activity-name) and share_content_page (h1.rich_media_title)
        h1 = soup.find(id='activity-name')
        nh = new_soup.find(id='activity-name')
        if h1 and nh:
            nh.clear()
            sp = new_soup.new_tag('span')
            sp['class'] = 'js_title_inner'
            sp.string = h1.get_text(strip=True)
            nh.append(sp)
        # Fallback for share_content_page template
        if not (h1 and nh):
            live_h1 = soup.find('h1')
            new_h1 = new_soup.find('h1')
            if live_h1 and new_h1:
                new_h1.string = live_h1.get_text(strip=True)

        # Author, time
        for eid in ['js_author_name_text','publish_time','js_name']:
            e1 = soup.find(id=eid); e2 = new_soup.find(id=eid)
            if e1 and e2 and e1.get_text(strip=True):
                e2.string = e1.get_text(strip=True)

        # Clean placeholder classes
        for img in new_soup.find_all('img'):
            cl = img.get('class', [])
            if isinstance(cl, str): cl = cl.split()
            nc = [c for c in cl if c not in ('js_img_placeholder','wx_img_placeholder')]
            if nc: img['class'] = ' '.join(nc)
            elif img.has_attr('class'): del img['class']

        result = str(new_soup)
        result = result.replace('大冲在思考', '沈理电协')
        result = re.sub(r'#imgIndex=\d+', '', result)
        result = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', result)
        result = result.replace('&amp;', '&')

        (article_dir / 'index.html').write_text(result, 'utf-8')

        # Fix remaining remote CDN URLs
        remotes = set(re.findall(r'https?://mmbiz\.qpic\.cn/[^"\'\s<>]+', result))
        remotes |= set(re.findall(r'https?://mmecoa\.qpic\.cn/[^"\'\s<>]+', result))
        if remotes:
            ridx = 1
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
                    if len(data) > 200:
                        ext = 'jpg'
                        if data[:4] == b'\x89PNG': ext = 'png'
                        elif data[:3] == b'GIF': ext = 'gif'
                        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP': ext = 'webp'
                        local = f'rem_{ridx}.{ext}'
                        (article_dir / local).write_bytes(data)
                        result = result.replace(url, local)
                        ridx += 1
            (article_dir / 'index.html').write_text(result, 'utf-8')

        # Download cover from og:image URL
        if og_img_url and og_img_url.startswith('http'):
            try:
                req = urllib.request.Request(og_img_url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://mp.weixin.qq.com/'
                })
                data = urllib.request.urlopen(req, timeout=15).read()
                if len(data) > 500:
                    (article_dir / 'cover.jpg').write_bytes(data)
                    print(f'Cover downloaded: {len(data)}B')
            except Exception as e:
                print(f'Cover download failed: {e}')

        # Fix og:image to cover.jpg
        html = (article_dir / 'index.html').read_text('utf-8')
        html = re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', html)
        html = re.sub(r'content="[^"]*"\s+property="twitter:image"', 'content="cover.jpg" property="twitter:image"', html)
        # Also check for double DOCTYPE
        html = html.replace('<!DOCTYPE html>', '', 1) if html.count('<!DOCTYPE html>') > 1 else html
        (article_dir / 'index.html').write_text(html, 'utf-8')

        # Clean up unused images
        refs = set()
        for m in re.finditer(r'img_\d+\.\w+', html): refs.add(m.group())
        for m in re.finditer(r'rem_\d+\.\w+', html): refs.add(m.group())
        for f in sorted(article_dir.iterdir()):
            if f.suffix in ('.jpg','.jpeg','.png','.gif','.webp','.svg','.bmp'):
                if f.name not in refs and f.name != 'cover.jpg':
                    f.unlink()

        final_html = (article_dir / 'index.html').read_text('utf-8')
        final_remote = len(re.findall(r'mmbiz\.qpic\.cn|mmecoa\.qpic\.cn', final_html))
        final_files = len(list(article_dir.iterdir()))
        print(f'Done: {final_files} files, {len(final_html)}B, {final_remote} remote')

        await browser.close()

asyncio.run(main())
