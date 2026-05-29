"""
Batch fix script for articles dated before 2023-03-23.

Steps:
1. Fix wrong image extensions (magic bytes check)  
2. Download remote CDN images via Playwright
3. Fix data-lazy-bgimg -> background-image
4. Remove placeholder classes (js_img_placeholder, etc.)
5. Fix og:image -> cover.jpg
6. Download video files
"""
import asyncio, json, re, base64, os
from pathlib import Path
from urllib.parse import urlparse, unquote

BASE = Path('D:/SLDX_Ambition_Website/doc/public/wechat/articles')
CUTOFF = '2023-03-23'

def get_article_dirs():
    dirs = []
    for d in BASE.iterdir():
        if not d.is_dir() or d.name.startswith('_'):
            continue
        m = re.match(r'^(\d{4}-\d{2}-\d{2})_', d.name)
        if m and m.group(1) < CUTOFF:
            dirs.append(d)
    return sorted(dirs)

def detect_ext(data):
    if data[:4] == b'\x89PNG': return 'png'
    if data[:6] == b'GIF89a' or data[:6] == b'GIF87a': return 'gif'
    if data[:2] == b'\xff\xd8': return 'jpg'
    if data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP': return 'webp'
    if data.startswith(b'<?xml') or data.startswith(b'<svg'): return 'svg'
    if data[:2] == b'BM': return 'bmp'
    return None

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'}

def fix_image_extensions(article_dirs):
    """Step 1: Fix images with wrong extensions."""
    fixed = 0
    for d in article_dirs:
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in IMG_EXTS:
                continue
            try:
                data = f.read_bytes()
                if len(data) < 50:
                    continue
                correct = detect_ext(data)
                if correct and f.suffix.lower() != f'.{correct}':
                    new_name = f.stem + f'.{correct}'
                    new_path = d / new_name
                    if not new_path.exists():
                        f.rename(new_path)
                        # Update HTML references
                        html_path = d / 'index.html'
                        if html_path.exists():
                            html = html_path.read_text('utf-8')
                            old_ref = f.name
                            if old_ref in html:
                                html = html.replace(old_ref, new_name)
                                html_path.write_text(html, 'utf-8')
                        fixed += 1
            except Exception as e:
                pass  # skip corrupted files
    return fixed

async def download_remote_images(article_dirs):
    """Step 2: Download remote CDN images via Playwright."""
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    # Collect all remote URLs
    remote_map = {}  # url -> set of (article_dir, attribute_name)
    for d in article_dirs:
        html_path = d / 'index.html'
        if not html_path.exists():
            continue
        html = html_path.read_text('utf-8')
        for m in re.finditer(r'https?://(?:mmbiz|mmecoa)\.qpic\.cn/[^"\'\s<>]+', html):
            url = m.group()
            url = url.rstrip(';,')  # clean trailing punctuation
            if url not in remote_map:
                remote_map[url] = set()
            remote_map[url].add(str(d))

    if not remote_map:
        print('  No remote CDN URLs found')
        return

    print(f'  {len(remote_map)} unique remote URLs across {len(set().union(*remote_map.values()))} articles')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
        )
        cf = Path('D:/SLDX_Ambition_Website/wechat-archive-tool/wechat_cookies.json')
        if cf.exists():
            try: await ctx.add_cookies(json.loads(cf.read_text()))
            except: pass

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        # Go to a WeChat page for proper Referer
        await page.goto('https://mp.weixin.qq.com/', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)

        downloaded = 0
        failed = 0
        batch_size = 20
        urls = list(remote_map.keys())

        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            tasks = []
            for url in batch:
                tasks.append(fetch_one(page, url))

            results = await asyncio.gather(*tasks)

            for url, data in zip(batch, results):
                if data and len(data) > 200:
                    ext = detect_ext(data) or 'jpg'
                    dirs_affected = remote_map[url]
                    for dir_str in dirs_affected:
                        d = Path(dir_str)
                        # Find next available img number
                        existing = list(d.glob('img_*'))
                        nums = []
                        for f in existing:
                            try:
                                n = int(re.match(r'img_(\d+)', f.stem).group(1))
                                nums.append(n)
                            except: pass
                        next_num = max(nums) + 1 if nums else 1
                        local = f'img_{next_num}.{ext}'
                        (d / local).write_bytes(data)
                        # Replace in HTML
                        html_path = d / 'index.html'
                        html = html_path.read_text('utf-8')
                        if url in html:
                            html = html.replace(url, local)
                            html_path.write_text(html, 'utf-8')
                    downloaded += 1
                else:
                    failed += 1

            print(f'    Batch {i//batch_size+1}/{ (len(urls)+batch_size-1)//batch_size }: {downloaded} ok, {failed} fail')
            await asyncio.sleep(1.5)  # rate limit

        await browser.close()
        return downloaded, failed

async def fetch_one(page, url):
    try:
        result = await page.evaluate("""async (url) => {
            try {
                const r = await fetch(url, {referrer: 'https://mp.weixin.qq.com/'});
                if (!r.ok) return null;
                const buf = await r.arrayBuffer();
                const bytes = new Uint8Array(buf);
                return Array.from(bytes);
            } catch(e) { return null; }
        }""", url)
        if result and len(result) > 200:
            return bytes(result)
    except:
        pass
    return None

def fix_data_lazy_bgimg(article_dirs):
    """Step 3: Fix data-lazy-bgimg -> background-image."""
    fixed = 0
    for d in article_dirs:
        html_path = d / 'index.html'
        if not html_path.exists():
            continue
        html = html_path.read_text('utf-8')
        changed = False

        # Replace data-lazy-bgimg="xxx" with background-image: url("xxx")
        soup = BeautifulSoup_wrapper(html)
        if soup:
            for tag in soup.find_all(attrs={'data-lazy-bgimg': True}):
                bg = tag.get('data-lazy-bgimg', '')
                if bg:
                    style = tag.get('style', '')
                    # Replace placeholder background-image with actual image
                    style = re.sub(
                        r'background-image:\s*url\(["\']?data:image/gif;base64,[^"\')\s]+["\']?\)',
                        f'background-image: url("{bg}")',
                        style
                    )
                    # Also set if no existing background-image
                    if 'background-image' not in style:
                        if style:
                            style += '; '
                        style += f'background-image: url("{bg}")'
                    tag['style'] = style
                    changed = True
                    fixed += 1

            if changed:
                result = str(soup)
                result = result.replace('&amp;', '&')
                html_path.write_text(result, 'utf-8')
    return fixed

def BeautifulSoup_wrapper(html):
    """Safe BeautifulSoup import."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'lxml')
    except:
        return None

def remove_placeholder_classes(article_dirs):
    """Step 4: Remove placeholder classes."""
    fixed = 0
    PLACEHOLDERS = {'js_img_placeholder', 'wx_img_placeholder', 'wx_imgbc_placeholder'}

    for d in article_dirs:
        html_path = d / 'index.html'
        if not html_path.exists():
            continue
        html = html_path.read_text('utf-8')
        changed = False

        # img class cleanup
        for match in re.finditer(r'(<img[^>]*class=")([^"]*)(")', html):
            classes = match.group(2).split()
            new_classes = [c for c in classes if c not in PLACEHOLDERS]
            if len(new_classes) != len(classes):
                old = match.group(0)
                if new_classes:
                    new_attr = f'{match.group(1)}{" ".join(new_classes)}{match.group(3)}'
                else:
                    # Remove class attribute entirely
                    new_attr = re.sub(r'\s*class="[^"]*"', '', match.group(0))
                html = html.replace(old, new_attr, 1)
                changed = True
                fixed += 1

        # Also handle div/section with wx_imgbc_placeholder
        for match in re.finditer(r'class="([^"]*wx_imgbc_placeholder[^"]*)"', html):
            classes = match.group(1).split()
            new_classes = [c for c in classes if c not in PLACEHOLDERS]
            if len(new_classes) != len(classes):
                old = match.group(0)
                if new_classes:
                    new_str = f'class="{" ".join(new_classes)}"'
                else:
                    new_str = ''
                html = html.replace(old, new_str, 1)
                changed = True

        if changed:
            html_path.write_text(html, 'utf-8')
    return fixed

def fix_og_image(article_dirs):
    """Step 5: Fix og:image to cover.jpg."""
    fixed = 0
    for d in article_dirs:
        html_path = d / 'index.html'
        if not html_path.exists():
            continue
        html = html_path.read_text('utf-8')

        # Check if og:image is remote
        if re.search(r'og:image[^>]*qpic\.cn', html) or re.search(r'qpic\.cn[^>]*og:image', html):
            if (d / 'cover.jpg').exists():
                html = re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', html)
                html = re.sub(r'content="[^"]*"\s+property="twitter:image"', 'content="cover.jpg" property="twitter:image"', html)
                # Also the other order
                html = re.sub(r'(og:image[^>]+content=)"[^"]*"', r'\1"cover.jpg"', html)
                html_path.write_text(html, 'utf-8')
                fixed += 1
    return fixed

async def download_videos(article_dirs):
    """Step 6: Download video files from WeChat pages."""
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    # Check which articles have videos
    video_dirs = []
    for d in article_dirs:
        html_path = d / 'index.html'
        if not html_path.exists():
            continue
        html = html_path.read_text('utf-8')
        if re.search(r'<mp-common-videosnap|<mpvideo\b|data-url="[^"]*finder', html):
            video_dirs.append(d)

    if not video_dirs:
        print('  No video articles found')
        return 0

    print(f'  {len(video_dirs)} articles with videos')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
        )
        cf = Path('D:/SLDX_Ambition_Website/wechat-archive-tool/wechat_cookies.json')
        if cf.exists():
            try: await ctx.add_cookies(json.loads(cf.read_text()))
            except: pass

        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        downloaded = 0
        for d in video_dirs:
            html_path = d / 'index.html'
            html = html_path.read_text('utf-8')

            # Find video URLs
            video_urls = set()
            for m in re.finditer(r'data-url="([^"]*finder[^"]*)"', html):
                video_urls.add(m.group(1).replace('&amp;', '&'))
            for m in re.finditer(r'data-feedcoverurl="([^"]*finder[^"]*)"', html):
                video_urls.add(m.group(1).replace('&amp;', '&'))

            if not video_urls:
                continue

            for url in list(video_urls)[:1]:  # Download first video per article
                try:
                    # Try to get video via WeChat page
                    data = await fetch_one(page, url)
                    if data and len(data) > 10000:
                        video_name = f'video_1.mp4'
                        (d / video_name).write_bytes(data)
                        # Update HTML - embed as video tag
                        html = re.sub(
                            r'<mp-common-videosnap[^>]*data-url="[^"]*"[^>]*>.*?</mp-common-videosnap>',
                            f'<video src="{video_name}" controls preload="metadata" style="width:100%;max-width:677px;"></video>',
                            html, count=1, flags=re.DOTALL
                        )
                        html_path.write_text(html, 'utf-8')
                        downloaded += 1
                except Exception as e:
                    pass

            await asyncio.sleep(1)  # Rate limit

        await browser.close()
        return downloaded

async def main():
    print('=' * 60)
    print('Batch Fix Script - Articles before 2023-03-23')
    print('=' * 60)

    article_dirs = get_article_dirs()
    print(f'Target articles: {len(article_dirs)}')

    # Step 1: Fix image extensions
    print('\n[1/6] Fixing wrong image extensions...')
    fixed = fix_image_extensions(article_dirs)
    print(f'  Fixed {fixed} images')

    # Step 2: Download remote CDN images
    print('\n[2/6] Downloading remote CDN images...')
    result = await download_remote_images(article_dirs)
    if result:
        dl, fail = result
        print(f'  Downloaded {dl}, failed {fail}')

    # Step 3: Fix data-lazy-bgimg
    print('\n[3/6] Fixing data-lazy-bgimg...')
    fixed = fix_data_lazy_bgimg(article_dirs)
    print(f'  Fixed {fixed} lazy-bgimg elements')

    # Step 4: Remove placeholder classes
    print('\n[4/6] Removing placeholder classes...')
    fixed = remove_placeholder_classes(article_dirs)
    print(f'  Fixed {fixed} elements')

    # Step 5: Fix og:image
    print('\n[5/6] Fixing og:image...')
    fixed = fix_og_image(article_dirs)
    print(f'  Fixed {fixed} articles')

    # Step 6: Download videos
    print('\n[6/6] Downloading videos...')
    await download_videos(article_dirs)

    print('\n' + '=' * 60)
    print('Done!')
    print('=' * 60)

if __name__ == '__main__':
    asyncio.run(main())
