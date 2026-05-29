"""Download + video fetch for 2022-03-01 article."""
import asyncio, re, json, shutil, struct, time
from pathlib import Path
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent))
from src.config import Config
from src.downloader import ArticleDownloader

URL = 'https://mp.weixin.qq.com/s/se4sF9Z5hBUGDwrrmzjPbg'
DIR_NAME = '2022-03-01_久等！RoboMaster_机甲大师_2021_赛季纪录预告片正式上线'
ARTICLE_BASE = Path('../doc/public/wechat/articles')
ARTICLE_OUT = ARTICLE_BASE / DIR_NAME

def detect_ext_from_bytes(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:3] == b'GIF': return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    return 'jpg'

def url_has_image_domain(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mpcdn', 'mmecoa.qpic.cn', 'res.wx.qq.com'])

def clean_url(url):
    return url.split('#')[0]

def parse_video_resolution(data):
    """Parse MP4 to get width,height."""
    offset = 0
    end = len(data)
    while offset + 8 <= end:
        size = struct.unpack('>I', data[offset:offset+4])[0]
        box_type = data[offset+4:offset+8].decode('ascii', errors='ignore')
        if size < 8: break
        header_size = 8
        if size == 1:
            size = struct.unpack('>Q', data[offset+8:offset+16])[0]
            header_size = 16
        box_end = min(offset + size, end)
        if box_type == 'tkhd':
            inner = data[offset+header_size:box_end]
            version = inner[0]
            pos = 4
            pos += 8 if version == 1 else 4
            pos += 8 if version == 1 else 4
            pos += 4; pos += 4
            pos += 8 if version == 1 else 4
            pos += 8; pos += 2+2+2+2; pos += 36
            w_raw = struct.unpack('>I', inner[pos:pos+4])[0]
            h_raw = struct.unpack('>I', inner[pos+4:pos+8])[0]
            return (w_raw >> 16, h_raw >> 16)
        elif box_type in ('moov','trak','mdia','minf','stbl'):
            r = parse_video_resolution(data[offset+header_size:box_end])
            if r: return r
        offset = box_end
    return None

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        cf = Path('wechat_cookies.json')
        if cf.exists():
            await ctx.add_cookies(json.loads(cf.read_text()))

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        config = Config()
        config._data['output_dir'] = '../doc/public/wechat'
        config._data['download_videos'] = False
        dl = ArticleDownloader(page, config)

        cdn_data = {}

        async def handle_response(response):
            u = response.url
            if not url_has_image_domain(u):
                return
            cu = clean_url(u)
            if cu in cdn_data:
                return
            try:
                body = await response.body()
                if body and len(body) > 200:
                    cdn_data[cu] = body
                    if cu.startswith('https://'):
                        cdn_data['http://' + cu[8:]] = body
                    elif cu.startswith('http://'):
                        cdn_data['https://' + cu[7:]] = body
            except Exception:
                pass

        page.on('response', handle_response)

        print('Loading article...', flush=True)
        await page.goto(URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        th = await page.evaluate('document.body.scrollHeight')
        for pos in range(0, th + 300, 300):
            await page.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.1)
        await asyncio.sleep(2)

        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        og_title = soup.find('meta', property='og:title')
        title = og_title['content'] if og_title else 'Untitled'
        og_image = soup.find('meta', property='og:image')
        og_image_url = og_image['content'] if og_image else None

        dl._fix_image_urls(soup)
        dl._clean_html(soup)

        if ARTICLE_OUT.is_dir():
            shutil.rmtree(str(ARTICLE_OUT))
        ARTICLE_OUT.mkdir(parents=True, exist_ok=True)

        # Collect image URLs
        all_cdn_urls = set()
        for img in soup.find_all('img'):
            src = img.get('src', '') or img.get('data-src', '')
            if url_has_image_domain(src):
                all_cdn_urls.add(clean_url(src))
        for tag in soup.find_all(style=True):
            st = tag.get('style', '')
            for m in re.finditer(r'background-image:\s*url\(["\']?(https?://[^"\')]+?)["\']?\)', st):
                if url_has_image_domain(m.group(1)):
                    all_cdn_urls.add(clean_url(m.group(1)))
        for tag in soup.find_all(attrs={'data-lazy-bgimg': True}):
            u = tag.get('data-lazy-bgimg', '')
            if url_has_image_domain(u):
                all_cdn_urls.add(clean_url(u))

        print(f'Images: intercepted={len(cdn_data)} refs={len(all_cdn_urls)}', flush=True)

        url_map = {}
        img_idx = 0
        for cdn_url in sorted(cdn_data.keys()):
            if cdn_url not in all_cdn_urls: continue
            data = cdn_data[cdn_url]
            ext = detect_ext_from_bytes(data)
            img_idx += 1
            fname = f'img_{img_idx}.{ext}'
            (ARTICLE_OUT / fname).write_bytes(data)
            url_map[cdn_url] = fname

        # Fallback
        missing = all_cdn_urls - set(url_map.keys())
        if missing:
            print(f'  {len(missing)} images fallback...', flush=True)
            for url in list(missing):
                try:
                    result = await page.evaluate("""async (url) => {
                        const r = await fetch(url); if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    }""", url)
                    if result and len(result) > 200:
                        data = bytes(result)
                        ext = detect_ext_from_bytes(data)
                        img_idx += 1
                        fname = f'img_{img_idx}.{ext}'
                        (ARTICLE_OUT / fname).write_bytes(data)
                        url_map[url] = fname
                except: pass

        # Replace image URLs in HTML
        for img in soup.find_all('img'):
            src = img.get('src', '')
            cu = clean_url(src)
            if cu in url_map: img['src'] = url_map[cu]
            ds = img.get('data-src', '')
            if ds and url_has_image_domain(ds):
                dc = clean_url(ds)
                if dc in url_map: img['data-src'] = url_map[dc]
        for tag in soup.find_all(style=True):
            st = tag.get('style', '')
            for cdn_url, local_fname in url_map.items():
                if cdn_url in st: st = st.replace(cdn_url, local_fname)
            tag['style'] = st
        for tag in soup.find_all(attrs={'data-lazy-bgimg': True}):
            bg = tag.get('data-lazy-bgimg', '')
            cu = clean_url(bg)
            if cu in url_map: tag['data-lazy-bgimg'] = url_map[cu]

        # Title
        for t in soup.find_all('title'): t.string = title
        if not soup.find('title'):
            head = soup.find('head')
            if head:
                t = soup.new_tag('title'); t.string = title; head.append(t)

        # Cover
        if og_image_url and url_has_image_domain(og_image_url):
            try:
                cover_data = cdn_data.get(clean_url(og_image_url))
                if not cover_data:
                    result = await page.evaluate("""async (url) => {
                        const r = await fetch(url); if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    }""", og_image_url)
                    if result and len(result) > 200: cover_data = bytes(result)
                if cover_data: (ARTICLE_OUT / 'cover.jpg').write_bytes(cover_data)
            except: pass

        html_str = str(soup).replace('大冲在思考', '沈理电协')
        html_str = html_str.replace('&amp;', '&')
        html_str = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', html_str)
        for cdn_url, local_fname in sorted(url_map.items(), key=lambda x: -len(x[0])):
            html_str = html_str.replace(cdn_url, local_fname)
            amp_url = cdn_url.replace('&', '&amp;')
            if amp_url != cdn_url: html_str = html_str.replace(amp_url, local_fname)

        html_str = re.sub(r'content="[^"]*mmbiz\.qpic\.cn[^"]*"\s+property="og:image"',
                          'content="cover.jpg" property="og:image"', html_str)
        html_str = re.sub(r'property="og:image"\s+content="[^"]*mmbiz\.qpic\.cn[^"]*"',
                          'property="og:image" content="cover.jpg"', html_str)
        (ARTICLE_OUT / 'index.html').write_text(html_str, encoding='utf-8')
        print(f'HTML saved: {len(html_str)}B', flush=True)

        # === Download video ===
        page2 = await ctx.new_page()
        await page2.goto(URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)
        th2 = await page2.evaluate('document.body.scrollHeight')
        for pos in range(0, th2 + 300, 300):
            await page2.evaluate(f'window.scrollTo(0, {pos})')
            await asyncio.sleep(0.1)
        await asyncio.sleep(3)

        video_info = await page2.evaluate('''() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return {src: v.src, duration: v.duration};
        }''')

        if video_info and video_info['src'] and 'mpvideo' in video_info['src']:
            print(f'Video: {video_info["duration"]:.1f}s, fetching...', flush=True)
            start = time.time()
            try:
                result = await page2.evaluate("""async (url) => {
                    const r = await fetch(url); if (!r.ok) return {status: r.status};
                    const buf = await r.arrayBuffer();
                    return {status: r.status, size: buf.byteLength, data: Array.from(new Uint8Array(buf))};
                }""", video_info['src'])
                print(f'  status={result["status"]} size={result["size"]} time={time.time()-start:.1f}s', flush=True)

                if result.get('data') and result['size'] > 100000:
                    data = bytes(result['data'])
                    (ARTICLE_OUT / 'video_1.mp4').write_bytes(data)

                    # Get resolution for aspect-ratio
                    res = parse_video_resolution(data)
                    if res:
                        w, h = res
                        print(f'  Resolution: {w}x{h}', flush=True)

                    # Update HTML: add video element
                    html2 = (ARTICLE_OUT / 'index.html').read_text(encoding='utf-8')
                    soup2 = BeautifulSoup(html2, 'lxml')

                    # Remove old broken video element if any
                    for v in soup2.find_all('video'):
                        v.decompose()

                    # Find #js_content to add video
                    js = soup2.find(id='js_content')
                    if js:
                        new_vid = soup2.new_tag('video')
                        new_vid['src'] = 'video_1.mp4'
                        new_vid['controls'] = ''
                        new_vid['preload'] = 'auto'
                        if res:
                            new_vid['style'] = f'width:100%;aspect-ratio:{w}/{h};display:block;background:#000'
                        else:
                            new_vid['style'] = 'width:100%;aspect-ratio:16/9;display:block;background:#000'
                        js.insert(0, new_vid)
                        print(f'  Video element added to #js_content', flush=True)

                    result_html = str(soup2).replace('&amp;', '&')
                    (ARTICLE_OUT / 'index.html').write_text(result_html, encoding='utf-8')
                else:
                    print(f'  Video download failed', flush=True)
            except Exception as e:
                print(f'  Video error: {e}', flush=True)
        else:
            print(f'  No video found on page', flush=True)

        await page2.close()
        await page.close()
        await browser.close()

        # Apply appmsg template
        print('\nApplying appmsg template...', flush=True)
        apply_template(ARTICLE_OUT)

        # Final check
        html_final = (ARTICLE_OUT / 'index.html').read_text(encoding='utf-8')
        remote = 'mmbiz.qpic.cn' in html_final or 'mpvideo.qpic.cn' in html_final
        vf = list(ARTICLE_OUT.glob('video_*.mp4'))
        vf_size = f'{vf[0].stat().st_size//1024}KB' if vf else 'none'
        print(f'Done: {len(list(ARTICLE_OUT.iterdir()))} files, video={vf_size}, remote={remote}', flush=True)

def apply_template(article_dir):
    """Apply appmsg template head."""
    import re as _re
    from pathlib import Path as _Path
    BASE2 = _Path('../doc/public/wechat/articles')
    REF_PREFIX = '2024-12-15_冬日畅言'

    hp = article_dir / 'index.html'
    h = hp.read_text(encoding='utf-8')
    rd = next(BASE2.glob(REF_PREFIX + '*'))
    rh = (rd / 'index.html').read_text(encoding='utf-8')
    rh = rh[:rh.find('</head>')]

    bs = h.find('<body')
    head = h[:bs]
    body = h[bs:]
    bte = body.find('>') + 1
    bt = body[:bte]
    bc = body[bte:]

    nh = rh
    meta_p = [
        (r'<title>(.*?)</title>', None),
        (r'property="og:title"\s+content="([^"]*)"', None),
        (r'property="og:url"\s+content="([^"]*)"', None),
        (r'property="og:image"\s+content="([^"]*)"', None),
        (r'name="twitter:image"\s+content="([^"]*)"', None),
        (r'name="description"\s+content="([^"]*)"', None),
        (r'property="og:description"\s+content="([^"]*)"', None),
        (r'name="author"\s+content="([^"]*)"', None),
    ]
    for pat, _ in meta_p:
        om = _re.search(pat, head)
        nm = _re.search(pat, nh)
        if om and nm and om.group(1) != nm.group(1):
            nh = nh.replace(nm.group(1), om.group(1))
    ot = _re.search(r'<title>(.*?)</title>', head)
    nt = _re.search(r'<title>(.*?)</title>', nh)
    if ot and nt and ot.group(1) != nt.group(1):
        nh = nh.replace(nt.group(0), ot.group(0))

    result = '<!DOCTYPE html>\n' + nh + '</head>\n' + bt + bc
    if result.count('<!DOCTYPE html>') > 1:
        result = result.replace('<!DOCTYPE html>', '', 1)
    if '<!DOCTYPE' in result and not result.startswith('<!DOCTYPE'):
        result = result[result.find('<!DOCTYPE'):]
    result = _re.sub(r'content="[^"]*mmbiz\.qpic\.cn[^"]*"', 'content="cover.jpg"', result)
    result = _re.sub(r'content="[^"]*mmecoa\.qpic\.cn[^"]*"', 'content="cover.jpg"', result)
    hp.write_text(result, encoding='utf-8')

asyncio.run(main())
