"""
Download videos from articles before 2023-04-01.
Handles both mp-common-videosnap and video_iframe types.
"""
import asyncio, re, sys, time, random, os
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

BASE = Path(__file__).parent.parent / 'doc' / 'public' / 'wechat' / 'articles'
CUTOFF = datetime(2023, 4, 1)
VIDEO_DIR = 'videos'

UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
]

def extract_dir_date(dirname):
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_', dirname)
    return datetime.strptime(m.group(1), '%Y-%m-%d') if m else None

def is_cdn(u):
    return any(d in u for d in ['mmbiz.qpic.cn', 'mmecoa.qpic.cn', 'mpcdn', 'res.wx.qq.com'])

def is_video_cdn(u):
    return any(d in u for d in ['video.qq.com', 'findermp.video.qq.com',
                                 'mp.weixin.qq.com/mp/readtemplate',
                                 'mpvideo.qpic.cn', 'vweixinfinder.video.qq.com'])

def build_list():
    articles = []
    for d in sorted(BASE.iterdir()):
        if not d.is_dir() or d.name.startswith('_'):
            continue
        dt = extract_dir_date(d.name)
        if not dt or dt >= CUTOFF:
            continue
        html = d / 'index.html'
        if not html.exists():
            continue
        h = html.read_text('utf-8', errors='ignore')
        if 'mp-common-videosnap' not in h and 'video_iframe' not in h:
            continue
        # Already has local video?
        has_local = bool(re.search(r'<video\s', h)) and 'mp.weixin' not in h.split('<video')[1] if '<video' in h else False
        if has_local:
            print(f'  SKIP (already local): {d.name[:50]}')
            continue
        articles.append(d)
    return articles

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    articles = build_list()
    print(f'Articles with remote videos: {len(articles)}')
    if not articles:
        print('Nothing to do.')
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=[
            f'--window-size={random.randint(1024,1920)},{random.randint(768,1080)}',
        ])
        ctx = await browser.new_context(
            user_agent=random.choice(UA_POOL),
            viewport={'width': random.randint(1024, 1920), 'height': random.randint(768, 1080)}
        )
        page = await ctx.new_page()
        stealth = Stealth(chrome_runtime=True, navigator_plugins=True)
        await stealth.apply_stealth_async(page)

        # Network interception for video files
        captured_videos = {}
        async def hdl(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'video' in ct or is_video_cdn(url):
                try:
                    body = await response.body()
                    if body and len(body) > 50000:
                        captured_videos[url] = body
                        print(f'    Captured video: {len(body)}B from {url[:80]}')
                except: pass
        page.on('response', hdl)

        total_ok = 0
        total_fail = 0

        for i, article_dir in enumerate(articles):
            html_path = article_dir / 'index.html'
            html = html_path.read_text('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'lxml')

            # Find og:url
            og_url_tag = soup.find('meta', property='og:url')
            wechat_url = og_url_tag['content'] if og_url_tag else None
            if not wechat_url:
                print(f'  [{i+1}/{len(articles)}] {article_dir.name[:50]} - NO og:url, skip')
                continue

            print(f'\n[{i+1}/{len(articles)}] {article_dir.name[:45]}')

            # Count video elements
            snaps = soup.find_all('mp-common-videosnap')
            viframes = soup.find_all('span', class_='video_iframe')
            print(f'  videosnap: {len(snaps)}  video_iframe: {len(viframes)}')

            captured_videos.clear()

            # Navigate to article page
            try:
                await page.goto(wechat_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
                # Scroll to trigger lazy video loading
                total_h = await page.evaluate('document.body.scrollHeight')
                for pos in range(0, total_h + 300, 300):
                    await page.evaluate(f'window.scrollTo(0, {pos})')
                    await asyncio.sleep(0.2)
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(3)
            except Exception as e:
                print(f'  Page load failed: {e}')
                total_fail += 1
                continue

            # Try to trigger video loading by clicking video_iframe elements
            if viframes:
                try:
                    # Navigate to the video player page for each video_iframe
                    for vf in viframes:
                        data_src = vf.get('data-src', '')
                        if data_src:
                            print(f'  Loading player: {data_src[:80]}...')
                            # Open player page in a new tab
                            vp = await ctx.new_page()
                            try:
                                await vp.goto(data_src, wait_until='domcontentloaded', timeout=20000)
                                await asyncio.sleep(5)
                                await vp.close()
                            except:
                                await vp.close()
                except Exception as e:
                    print(f'  Video player load error: {e}')

            # Get live page HTML to extract video URLs
            live_html = await page.content()
            live_soup = BeautifulSoup(live_html, 'lxml')

            # Collect all video URLs from the live page
            video_urls = set()

            # From mp-common-videosnap
            for snap in live_soup.find_all('mp-common-videosnap'):
                durl = snap.get('data-url', '')
                if durl and 'video' in durl:
                    video_urls.add(durl)

            # From video_iframe data-src
            for vf in live_soup.find_all('span', class_='video_iframe'):
                for attr in ['data-src', 'data-url']:
                    val = vf.get(attr, '')
                    if val and 'mp.weixin.qq.com' in val:
                        video_urls.add(val)

            # Also grab video URLs from the page's JS/embedded data
            for m in re.finditer(r'video_url["\']?\s*[:=]\s*["\'](https?://[^"\']+\.mp4[^"\']*)', live_html):
                video_urls.add(m.group(1))
            for m in re.finditer(r'src=["\'](https?://[^"\']*video[^"\']*)["\']', live_html):
                u = m.group(1)
                if any(d in u for d in ['.mp4', 'video.qq.com', 'mpvideo']):
                    video_urls.add(u)

            print(f'  Video URLs found: {len(video_urls)}')

            # Download each video
            video_files = []
            for j, vurl in enumerate(sorted(video_urls)):
                # First check if captured by network interception
                data = captured_videos.get(vurl)
                if not data:
                    # Try fetching directly
                    try:
                        result = await page.evaluate("""async (url) => {
                            try {
                                const r = await fetch(url);
                                if (!r.ok) return null;
                                const buf = await r.arrayBuffer();
                                return Array.from(new Uint8Array(buf));
                            } catch(e) { return null; }
                        }""", vurl)
                        if result and len(result) > 50000:
                            data = bytes(result)
                    except: pass

                if data and len(data) > 50000:
                    local_name = f'video_{j+1}.mp4'
                    local_path = article_dir / local_name
                    local_path.write_bytes(data)
                    video_files.append((vurl, local_name, len(data)))
                    print(f'    Downloaded: {local_name} ({len(data)//1024}KB)')
                elif not is_cdn(vurl) and 'mp.weixin.qq.com' not in vurl:
                    # Direct CDN URL - try aiohttp as fallback
                    video_files.append((vurl, vurl.split('?')[0].split('/')[-1][:40], 0))
                    print(f'    URL saved (to download manually): {vurl[:100]}')

            # Replace video elements in HTML with local versions
            if video_files:
                vf_idx = 0
                # Replace mp-common-videosnap
                for snap in soup.find_all('mp-common-videosnap'):
                    if vf_idx < len(video_files):
                        _, local_name, _ = video_files[vf_idx]
                        video_tag = soup.new_tag('video')
                        video_tag['src'] = local_name
                        video_tag['controls'] = ''
                        video_tag['style'] = 'max-width:100%;width:100%'
                        video_tag.string = ''
                        snap.replace_with(video_tag)
                        vf_idx += 1

                # Replace video_iframe
                for vf in soup.find_all('span', class_='video_iframe'):
                    if vf_idx < len(video_files):
                        _, local_name, _ = video_files[vf_idx]
                        video_tag = soup.new_tag('video')
                        video_tag['src'] = local_name
                        video_tag['controls'] = ''
                        video_tag['style'] = 'max-width:100%;width:100%'
                        video_tag.string = ''
                        parent = vf.parent
                        vf.replace_with(video_tag)
                        # Remove empty parent sections
                        if parent and parent.name == 'section' and not parent.get_text(strip=True) and not parent.find_all('img'):
                            parent.decompose()

                result_html = str(soup)
                result_html = result_html.replace('&amp;', '&')
                html_path.write_text(result_html, 'utf-8')
                print(f'  HTML updated: {len(video_files)} videos')
                total_ok += 1
            else:
                print(f'  No videos downloaded')
                total_fail += 1

            time.sleep(2)

        await page.close()
        await ctx.close()
        await browser.close()

    print(f'\n=== DONE ===')
    print(f'OK: {total_ok}  Failed: {total_fail}')

if __name__ == '__main__':
    asyncio.run(main())
