"""
Batch re-download script: opens each article on WeChat, intercepts images via network,
saves with correct format. Resumable with checkpointing.

Usage: python batch_redownload.py
  - First run creates checkpoint file
  - Interrupted? Just run again (resumes from checkpoint)
"""
import asyncio, json, re, time
from pathlib import Path
from bs4 import BeautifulSoup

BASE = Path('D:/SLDX_Ambition_Website/doc/public/wechat/articles')
CUTOFF = '2023-03-23'
CHECKPOINT = Path('D:/SLDX_Ambition_Website/wechat-archive-tool/batch_checkpoint.json')
CONCURRENT = 1  # parallel article downloads
TEST_MODE = False  # Set to True for testing with 3 articles

def get_pending_articles():
    """Get articles that need re-download (have images or CDN refs)."""
    done = set()
    if CHECKPOINT.exists():
        done = set(json.loads(CHECKPOINT.read_text()))
    
    all_dirs = []
    skipped_no_images = 0
    for d in BASE.iterdir():
        if not d.is_dir() or d.name.startswith('_'):
            continue
        m = re.match(r'^(\d{4}-\d{2}-\d{2})_', d.name)
        if m and m.group(1) < CUTOFF:
            if d.name in done:
                continue
            html_path = d / 'index.html'
            has_imgs = len(list(d.glob('img_*'))) > 0
            has_remote = False
            if html_path.exists():
                html = html_path.read_text('utf-8')[:50000]
                has_remote = bool(re.search(r'mmbiz\.qpic\.cn|mmecoa\.qpic\.cn', html))
            
            if not has_imgs and not has_remote:
                skipped_no_images += 1
                done.add(d.name)
                continue
            
            # Re-download ALL articles with images (not just those with remote CDN)
            # because format issues may exist even when images are local
            
            all_dirs.append(d)
    
    if skipped_no_images or len(all_dirs) < len(done):
        CHECKPOINT.write_text(json.dumps(list(done)))
    
    return all_dirs, done

def detect_ext(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:6] in (b'GIF89a', b'GIF87a'): return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    return 'jpg'

def is_cdn(url):
    return any(d in url for d in ['mmbiz.qpic.cn', 'mmecoa.qpic.cn', 'mpcdn'])

async def process_one_article(d, page, template_html_appmsg, template_html_share):
    """Download one article from WeChat and rebuild with template head."""
    html_path = d / 'index.html'
    if not html_path.exists():
        return False, "no index.html"
    
    old_html = html_path.read_text('utf-8')
    
    # Get og:url
    og_match = re.search(r'og:url[^>]+content="([^"]+)"', old_html)
    if not og_match:
        og_match = re.search(r'content="([^"]+)"[^>]*og:url', old_html)
    if not og_match:
        return False, "no og:url"
    
    article_url = og_match.group(1).replace('&amp;', '&')
    if not article_url.startswith('http'):
        return False, "bad url"
    
    # Get og:image URL FIRST
    og_img_match = re.search(r'og:image[^>]+content="([^"]+)"', old_html)
    if not og_img_match:
        og_img_match = re.search(r'content="([^"]+)"[^>]*og:image', old_html)
    og_img_orig = og_img_match.group(1) if og_img_match else None
    
    # Network interception - use a flag to collect
    captured = {}
    intercept_active = True
    
    async def hdl(response):
        if not intercept_active:
            return
        url = response.url
        if response.status == 200 and is_cdn(url):
            try:
                body = await response.body()
                if body and len(body) > 200:
                    captured[url] = body
                    captured[url.split('?')[0]] = body
            except: pass
    
    page.on('response', hdl)
    
    try:
        await page.goto(article_url, wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(2)
        
        # Quick scroll for lazy images
        for i in range(8):
            await page.evaluate(f'window.scrollTo(0, {i * 800})')
            await asyncio.sleep(0.3)
        await asyncio.sleep(1)
        
        html = await page.content()
    except Exception as e:
        # Retry once for execution context errors
        if 'execution context' in str(e).lower():
            try:
                await asyncio.sleep(1)
                await page.goto(article_url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)
                html = await page.content()
            except Exception as e2:
                intercept_active = False
                return False, f"goto failed (retry): {e2}"
        else:
            intercept_active = False
            return False, f"goto failed: {e}"
    
    intercept_active = False
    
    soup = BeautifulSoup(html, 'lxml')
    js = soup.find(id='js_content')
    
    if not js or len(str(js)) < 2000:
        return False, "empty js_content"
    
    # Detect article type - check body, not CSS
    body = soup.find('body')
    body_class = ' '.join(body.get('class', [])) if body else ''
    is_share_content = 'share_content_page' in body_class
    
    # Collect CDN URLs from js_content
    all_urls = set()
    for img in js.find_all('img'):
        for attr in ['src', 'data-src']:
            val = img.get(attr, '')
            if val and is_cdn(val):
                val = ('https:' + val) if val.startswith('//') else val
                all_urls.add(val)
    
    for tag in js.find_all(style=True):
        st = tag.get('style', '')
        for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
            if is_cdn(m.group(1)):
                all_urls.add(m.group(1).replace('&amp;', '&'))
    
    for tag in js.find_all(attrs={'data-lazy-bgimg': True}):
        u = tag.get('data-lazy-bgimg', '')
        if is_cdn(u):
            u = ('https:' + u) if u.startswith('//') else u
            all_urls.add(u)
    
    # Delete old images and save new ones
    for f in d.glob('img_*'): f.unlink()
    for f in d.glob('rem_*'): f.unlink()
    
    url_map = {}
    for url in sorted(all_urls):
        data = captured.get(url) or captured.get(url.split('?')[0])
        if not data and is_cdn(url):
            # Fallback: fetch via page.evaluate
            try:
                result = await page.evaluate("""async (url) => {
                    try { const r = await fetch(url);
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", url)
                if result and len(result) > 200:
                    data = bytes(result)
            except: pass
        
        if data and len(data) > 200:
            ext = detect_ext(data)
            local = f'img_{len(url_map)+1}.{ext}'
            (d / local).write_bytes(data)
            url_map[url] = local
    
    # Replace URLs in js_content
    for img in js.find_all('img'):
        for attr in ['src', 'data-src']:
            val = img.get(attr, '')
            if val and is_cdn(val):
                val = ('https:' + val) if val.startswith('//') else val
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
    
    # Build new HTML with correct template
    template_html = template_html_share if is_share_content else template_html_appmsg
    new_soup = BeautifulSoup(template_html, 'lxml')
    
    # Metadata
    for meta_name, attr in [('og:title','property'),('og:url','property'),
                             ('og:description','property'),('og:site_name','property'),
                             ('og:type','property'),('og:article:author','property'),
                             ('twitter:title','property'),('twitter:site','property'),
                             ('twitter:creator','property'),('twitter:description','property'),
                             ('twitter:card','property'),
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
    
    # js_content
    nj = new_soup.find(id='js_content')
    if nj:
        nj.clear()
        for c in list(js.contents):
            try: nj.append(c)
            except:
                cc = BeautifulSoup(str(c), 'lxml').find()
                if cc: nj.append(cc)
    
    # H1
    h1 = soup.find(id='activity-name')
    nh = new_soup.find(id='activity-name')
    if h1 and nh:
        nh.clear()
        sp = new_soup.new_tag('span')
        sp['class'] = 'js_title_inner'
        sp.string = h1.get_text(strip=True) or (og_ti['content'] if og_ti else '')
        nh.append(sp)
    
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
    result = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', result)
    result = result.replace('&amp;', '&')
    result = result.replace('<!DOCTYPE html>', '', 1) if result.count('<!DOCTYPE html>') > 1 else result
    
    html_path.write_text(result, 'utf-8')
    
    # Download cover
    if og_img_orig and og_img_orig.startswith('http') and is_cdn(og_img_orig):
        try:
            cover_data = captured.get(og_img_orig) or captured.get(og_img_orig.split('?')[0])
            if not cover_data:
                result = await page.evaluate("""async (url) => {
                    try { const r = await fetch(url);
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    return Array.from(new Uint8Array(buf));
                    } catch(e) { return null; }
                }""", og_img_orig)
                if result: cover_data = bytes(result)
            if cover_data and len(cover_data) > 500:
                (d / 'cover.jpg').write_bytes(cover_data)
        except: pass
    
    # Fix og:image in final HTML
    rhtml = html_path.read_text('utf-8')
    rhtml = re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', rhtml)
    rhtml = re.sub(r'content="[^"]*"\s+property="twitter:image"', 'content="cover.jpg" property="twitter:image"', rhtml)
    html_path.write_text(rhtml, 'utf-8')
    
    # Cleanup unused
    refs = set()
    for m in re.finditer(r'img_\d+\.\w+', rhtml): refs.add(m.group())
    for m in re.finditer(r'rem_\d+\.\w+', rhtml): refs.add(m.group())
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp','.svg','.bmp'):
            if f.name not in refs and f.name != 'cover.jpg':
                f.unlink()
    
    remote = len(re.findall(r'mmbiz\.qpic\.cn|mmecoa\.qpic\.cn', rhtml))
    return True, f"{len(url_map)} imgs, {len(rhtml)}B, {remote} remote, type={'share' if is_share_content else 'appmsg'}"

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth
    
    pending, done = get_pending_articles()
    print(f'Pending: {len(pending)}, Already done: {len(done)}')
    
    if TEST_MODE:
        pending = pending[:3]  # Test with 3 articles first
        print(f'TEST MODE: only processing {len(pending)} articles')
    
    if not pending:
        print('All done!')
        return
    
    # Load templates
    template_appmsg = None
    template_share = None
    for d in BASE.iterdir():
        if d.is_dir() and '冬日畅言' in d.name:
            template_appmsg = (d / 'index.html').read_text('utf-8')
        if d.is_dir() and '小雪伊始' in d.name:
            template_share = (d / 'index.html').read_text('utf-8')
    if not template_appmsg or not template_share:
        print('ERROR: Could not find template articles')
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
        )
        cf = Path('D:/SLDX_Ambition_Website/wechat-archive-tool/wechat_cookies.json')
        if cf.exists():
            try: await ctx.add_cookies(json.loads(cf.read_text()))
            except: pass
        
        # Create multiple pages for concurrency
        pages = []
        for _ in range(CONCURRENT):
            page = await ctx.new_page()
            stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
            await stealth.apply_stealth_async(page)
            pages.append(page)
        
        ok = 0
        fail = 0
        start_time = time.time()
        
        for i, d in enumerate(pending):
            page = pages[i % CONCURRENT]
            
            try:
                print(f'[{i+1}/{len(pending)}] {d.name[:60]}... ', end='', flush=True)
            except UnicodeEncodeError:
                safe_name = d.name.encode('ascii', 'replace').decode('ascii')[:60]
                print(f'[{i+1}/{len(pending)}] {safe_name}... ', end='', flush=True)
            success, msg = await process_one_article(d, page, template_appmsg, template_share)
            
            if success:
                ok += 1
                done.add(d.name)
                # Checkpoint every 10 articles
                if ok % 10 == 0:
                    CHECKPOINT.write_text(json.dumps(list(done)))
            else:
                fail += 1
            
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i - 1) / rate if rate > 0 else 0
            try:
                print(f'{msg} | ok={ok} fail={fail} | {rate*60:.1f}/min ETA {eta/60:.1f}min')
            except UnicodeEncodeError:
                print(f'(unicode) | ok={ok} fail={fail} | {rate*60:.1f}/min ETA {eta/60:.1f}min')
            
            # Rate limiting between articles
            await asyncio.sleep(1)
        
        # Final checkpoint
        CHECKPOINT.write_text(json.dumps(list(done)))
        await browser.close()
    
    print(f'\nDone! ok={ok} fail={fail} total={ok+fail}')

if __name__ == '__main__':
    asyncio.run(main())
