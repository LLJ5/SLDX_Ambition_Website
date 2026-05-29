"""Fix remaining issues in the re-downloaded article."""
import re, asyncio, json, base64
from pathlib import Path
from bs4 import BeautifulSoup

DIR_NAME = '2025-03-24_2025高校联盟赛内地站日程与参赛名单公布'
BASE = Path('D:/SLDX_Ambition_Website/doc/public/wechat/articles')
ARTICLE_DIR = BASE / DIR_NAME

async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    html_path = ARTICLE_DIR / 'index.html'
    html = html_path.read_text(encoding='utf-8')

    # 1. Fix filename parameter pollution
    html = re.sub(r'(img_\d+\.\w+)&[^"\s]+', r'\1', html)
    html = re.sub(r'(rem_\d+\.\w+)&[^"\s]+', r'\1', html)
    print('Fixed filename parameters')

    # 2. Find remaining remote CDN URLs
    remotes = set(re.findall(r'https?://mmbiz\.qpic\.cn/[^"\'\s<>]+', html))
    print(f'Remote CDN URLs: {len(remotes)}')
    for u in remotes:
        print(f'  {u[:120]}')

    if remotes:
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

            # Go to article page for Referer
            og_url = re.search(r'og:url[^>]+content="([^"]+)"', html)
            if og_url:
                try:
                    await page.goto(og_url.group(1).replace('&amp;', '&'), wait_until='domcontentloaded', timeout=15000)
                except:
                    pass

            idx = 1
            for url in remotes:
                print(f'Fetching: {url[:80]}...')
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
                        elif data.startswith(b'<?xml') or data.startswith(b'<svg'): ext = 'svg'

                        local = f'img_{64 + idx}.{ext}'
                        (ARTICLE_DIR / local).write_bytes(data)
                        html = html.replace(url, local)
                        # Also replace // variant
                        if url.startswith('https:'):
                            html = html.replace('//' + url[8:], local)
                        print(f'  Saved as {local}')
                        idx += 1

            await browser.close()

    # 3. Fix og:image - should be cover.jpg
    if (ARTICLE_DIR / 'cover.jpg').exists():
        html = re.sub(r'content="[^"]*"\s+property="og:image"', 'content="cover.jpg" property="og:image"', html)
        html = re.sub(r'content="[^"]*"\s+property="twitter:image"', 'content="cover.jpg" property="twitter:image"', html)
        print('Fixed og:image to cover.jpg')

    # 4. Clean up unused image files
    refs = set()
    for m in re.finditer(r'<img[^>]+src="([^"]+)"', html):
        refs.add(m.group(1))
    for m in re.finditer(r'url\("?([^")]+)"?\)', html):
        u = m.group(1)
        if not u.startswith('http') and not u.startswith('../'):
            refs.add(u)
    for m in re.finditer(r'data-lazy-bgimg="([^"]+)"', html):
        refs.add(m.group(1))
    og = re.search(r'og:image[^>]+content="([^"]+)"', html)
    if og: refs.add(og.group(1))

    refs = {r.split('&')[0] for r in refs}  # clean params

    removed = 0
    for f in sorted(ARTICLE_DIR.iterdir()):
        if f.suffix in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'):
            if f.name not in refs and f.name != 'cover.jpg':
                f.unlink()
                removed += 1
                print(f'Removed unused: {f.name}')

    print(f'\nRemoved {removed} unused images')

    # 5. Final check
    final_remotes = len(re.findall(r'mmbiz\.qpic\.cn', html))
    print(f'Final remote CDN refs: {final_remotes}')
    print(f'Final HTML size: {len(html)}B')

    # Fix double DOCTYPE
    html = re.sub(r'<!DOCTYPE html>', '', html, count=1) if html.count('<!DOCTYPE html>') > 1 else html
    html_path.write_text(html, encoding='utf-8')
    print(f'Saved to {html_path}')

    # List remaining files
    files = sorted(ARTICLE_DIR.iterdir())
    print(f'\nRemaining files ({len(files)}):')
    for f in files:
        print(f'  {f.name}')

if __name__ == '__main__':
    asyncio.run(main())
