"""Re-download 2025高校联盟赛内地站点日程与参赛名单公布."""
import asyncio, json, re, base64
from pathlib import Path
from bs4 import BeautifulSoup

URL = 'https://mp.weixin.qq.com/s?__biz=MzAwMDM4NTYzMQ==&mid=2693317775&idx=1&sn=9373fe77a7e01351a92da0135581cd6b&chksm=be04726ff061d5c52611232ae361d58d007564484474fe4382477cb132c6332fd9c96502eda8#rd'

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

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
        cf = Path(r'D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json')
        if cf.exists():
            try:
                await ctx.add_cookies(json.loads(cf.read_text()))
            except:
                pass

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        # Network interception
        captured = {}
        async def hdl(r):
            u = r.url
            if r.status == 200 and 'mmbiz.qpic.cn' in u:
                try:
                    body = await r.body()
                    if len(body) > 200:
                        captured[u] = body
                        captured[u.split('?')[0]] = body
                except:
                    pass
        page.on('response', hdl)

        print('Loading article...')
        await page.goto(URL, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)

        # Scroll to trigger lazy images
        for i in range(20):
            await page.evaluate(f'window.scrollTo(0, {i * 600})')
            await asyncio.sleep(0.5)
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(3)

        live = await page.content()
        soup = BeautifulSoup(live, 'lxml')
        js = soup.find(id='js_content')

        if not js or len(str(js)) < 2000:
            print('WARNING: live page has no js_content, skipping to avoid corruption')
            await browser.close()
            return

        print(f'Content: {len(str(js))} html chars, {len(js.find_all("img"))} imgs, {len(captured)} captured')

        # Find template article (appmsg type → use 2024-12-15)
        template_dir = find_dir('2024-12-15')
        if not template_dir:
            # Fallback: use any article
            for d in sorted(BASE.iterdir(), reverse=True):
                if d.is_dir() and (d / 'index.html').exists():
                    template_dir = d
                    break

        if not template_dir:
            print('ERROR: No template article found')
            await browser.close()
            return

        template_html = (template_dir / 'index.html').read_text(encoding='utf-8')
        print(f'Using template: {template_dir.name}')

        # Find article directory (target the specific 2025 "内地站" article)
        article_dir = find_dir('内地站日程')
        if not article_dir:
            print('ERROR: Article directory not found')
            await browser.close()
            return

        print(f'Article dir: {article_dir.name}')

        # Collect all image URLs from content
        all_urls = set()
        for img in js.find_all('img'):
            for attr in ['src', 'data-src']:
                val = img.get(attr, '')
                if val and 'mmbiz.qpic.cn' in val and not val.startswith('data:'):
                    if val.startswith('//'):
                        val = 'https:' + val
                    all_urls.add(val)

        # Also collect from style attributes
        for tag in js.find_all(style=True):
            st = tag.get('style', '')
            for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
                if 'mmbiz.qpic.cn' in m.group(1):
                    u = m.group(1)
                    if u.startswith('//'):
                        u = 'https:' + u
                    all_urls.add(u)

        # Collect from data-lazy-bgimg
        for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
            u = tag.get('data-lazy-bgimg', '')
            if 'mmbiz.qpic.cn' in u:
                if u.startswith('//'):
                    u = 'https:' + u
                all_urls.add(u)

        print(f'CDN URLs found: {len(all_urls)}')

        # Save images
        url_to_local = {}
        idx = 1
        for url in sorted(all_urls):
            data = captured.get(url) or captured.get(url.split('?')[0])
            if data and len(data) > 200:
                ext = 'jpg'
                if data[:4] == b'\x89PNG':
                    ext = 'png'
                elif data[:3] == b'GIF':
                    ext = 'gif'
                elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                    ext = 'webp'
                elif data.startswith(b'<?xml') or data.startswith(b'<svg'):
                    ext = 'svg'
                local = f'img_{idx}.{ext}'
                (article_dir / local).write_bytes(data)
                url_to_local[url] = local
                idx += 1

        print(f'Saved {len(url_to_local)} images')

        # Replace URLs in content
        def replace_urls_in_tag(tag):
            # Replace in src/data-src
            for attr in ['src', 'data-src']:
                val = tag.get(attr, '')
                if val and 'mmbiz.qpic.cn' in val:
                    if val.startswith('//'):
                        val = 'https:' + val
                    for cdn, local in url_to_local.items():
                        if val == cdn or val == cdn.split('?')[0]:
                            tag[attr] = local
                            break

            # Replace in style
            st = tag.get('style', '')
            for cdn, local in url_to_local.items():
                if cdn in st:
                    st = st.replace(cdn, local)
                    # Also handle // variant
                    st = st.replace('//' + cdn[8:], local)
            tag['style'] = st

            # Replace data-lazy-bgimg
            bg = tag.get('data-lazy-bgimg', '')
            for cdn, local in url_to_local.items():
                if cdn in bg:
                    tag['data-lazy-bgimg'] = local
                    break

        for tag in js.find_all(['img', 'svg', 'section']):
            replace_urls_in_tag(tag)

        # Also replace bg images in all tags
        for tag in js.find_all(style=True):
            st = tag.get('style', '')
            for m in re.finditer(r'background-image:\s*url\(["\']?([^"\')]+?)["\']?\)', st):
                bg_url = m.group(1)
                if 'mmbiz.qpic.cn' in bg_url:
                    for cdn, local in url_to_local.items():
                        if cdn in bg_url or cdn.split('?')[0] in bg_url:
                            st = st.replace(bg_url, local)
            tag['style'] = st

        # Build new HTML using template
        new_soup = BeautifulSoup(template_html, 'lxml')

        # Replace metadata
        for meta_name, attr in [('og:title', 'property'), ('og:url', 'property'),
                                 ('og:image', 'property'), ('og:description', 'property'),
                                 ('og:article:author', 'property'), ('og:site_name', 'property'),
                                 ('og:type', 'property'),
                                 ('twitter:title', 'property'), ('twitter:image', 'property'),
                                 ('twitter:creator', 'property'), ('twitter:site', 'property'),
                                 ('twitter:description', 'property'),
                                 ('description', 'name'), ('author', 'name')]:
            src_tag = soup.find('meta', attrs={attr: meta_name})
            dst_tag = new_soup.find('meta', attrs={attr: meta_name})
            if src_tag and dst_tag and src_tag.get('content'):
                dst_tag['content'] = src_tag['content']

        # Replace title
        title_tag = new_soup.find('title')
        og_title = soup.find('meta', property='og:title')
        if title_tag and og_title and og_title.get('content'):
            title_tag.string = og_title['content']

        # Replace body content
        new_js = new_soup.find(id='js_content')
        if new_js:
            new_js.clear()
            for c in list(js.contents):
                new_js.append(c)

        # Update H1 title
        h1 = soup.find(id='activity-name')
        nh = new_soup.find(id='activity-name')
        if h1 and nh:
            nh.clear()
            sp = new_soup.new_tag('span')
            sp['class'] = 'js_title_inner'
            sp.string = h1.get_text(strip=True)
            nh.append(sp)

        # Update author, time, js_name
        for eid in ['js_author_name_text', 'publish_time', 'js_name']:
            e1 = soup.find(id=eid)
            e2 = new_soup.find(id=eid)
            if e1 and e2 and e1.get_text(strip=True):
                e2.string = e1.get_text(strip=True)

        # Clean placeholder classes from images
        for img in new_soup.find_all('img'):
            cl = img.get('class', [])
            if isinstance(cl, str):
                cl = cl.split()
            nc = [c for c in cl if c not in ('js_img_placeholder', 'wx_img_placeholder')]
            if nc:
                img['class'] = ' '.join(nc)
            elif img.has_attr('class'):
                del img['class']

        # Clean wx_imgbc_placeholder
        for tag in new_soup.find_all(attrs={'class': True}):
            cl = tag.get('class', [])
            if isinstance(cl, str):
                cl = cl.split()
            if 'wx_imgbc_placeholder' in cl:
                nc = [c for c in cl if c != 'wx_imgbc_placeholder']
                if nc:
                    tag['class'] = ' '.join(nc)
                else:
                    del tag['class']

        result = str(new_soup)
        result = result.replace('大冲在思考', '沈理电协')
        result = re.sub(r'#imgIndex=\d+', '', result)
        result = result.replace('&amp;', '&')

        (article_dir / 'index.html').write_text(result, encoding='utf-8')

        remote = len(re.findall(r'mmbiz\.qpic\.cn', result))
        print(f'Done: {len(url_to_local)} imgs, {remote} remote CDN, {len(result)}B')

        # In-browser fetch for remaining remote URLs
        if remote > 0:
            print('Fetching remaining remote images via browser...')
            html = (article_dir / 'index.html').read_text(encoding='utf-8')
            remotes = set(re.findall(r'https?://mmbiz\.qpic\.cn/[^"\'\s<>]+', html))
            rem_idx = 1
            for url in list(remotes):
                if url not in captured:
                    captured[url] = captured.get(url, None)
                data = captured.get(url) or captured.get(url.split('?')[0])
                if not data:
                    try:
                        du = await page.evaluate("""async (url) => {
                            try { const r = await fetch(url); if (!r.ok) return null;
                            const b = await r.blob();
                            return new Promise(res => { const fr = new FileReader();
                            fr.onloadend = () => res(fr.result); fr.readAsDataURL(b); });
                            } catch(e) { return null; }
                        }""", url)
                        if du and 'data:' in du:
                            data = base64.b64decode(du.split(',', 1)[1])
                    except:
                        pass

                if data and len(data) > 200:
                    ext = 'jpg'
                    if data[:4] == b'\x89PNG':
                        ext = 'png'
                    elif data[:3] == b'GIF':
                        ext = 'gif'
                    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                        ext = 'webp'
                    elif data.startswith(b'<?xml') or data.startswith(b'<svg'):
                        ext = 'svg'
                    local = f'rem_{rem_idx}.{ext}'
                    (article_dir / local).write_bytes(data)
                    html = html.replace(url, local)
                    rem_idx += 1

            (article_dir / 'index.html').write_text(html, encoding='utf-8')
            final = len(re.findall(r'mmbiz\.qpic\.cn', html))
            print(f'Final remote: {final}')

        await browser.close()

asyncio.run(main())
