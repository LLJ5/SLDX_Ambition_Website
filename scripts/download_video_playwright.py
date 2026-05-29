"""
V5: Use page.expose_function + route interception for proper video capture.
Or simply use Playwright to get fresh tokens, then aiohttp.
"""
import os
import re
import sys
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ARTICLE_URL = "https://mp.weixin.qq.com/s/be4l_9rWF541w39HdrBlHA"
ARTICLE_DIR = r"D:\SLDX_Ambition_Website\doc\public\wechat\articles\2023-03-29_哨兵组专访"
HTML_PATH = os.path.join(ARTICLE_DIR, "index.html")
COOKIE_FILE = r"D:\SLDX_Ambition_Website\wechat-archive-tool\wechat_cookies.json"
TARGET_VIDS = {"wxv_2859238637077626882", "wxv_2859240235946311683"}


async def main():
    print("=" * 60)
    print("Video Download: 哨兵组专访")
    print("=" * 60)

    if not os.path.exists(COOKIE_FILE):
        print(f"[ERROR] No cookies: {COOKIE_FILE}")
        sys.exit(1)

    with open(COOKIE_FILE, encoding="utf-8") as f:
        cookies_data = json.load(f)

    downloaded = {}
    download_done = asyncio.Event()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        await context.add_cookies(cookies_data)
        page = await context.new_page()

        # Use route interception to capture video responses
        async def handle_route(route):
            url = route.request.url
            for vid in TARGET_VIDS:
                if f"vid={vid}" in url and vid not in downloaded:
                    print(f"  [INTERCEPT] {vid}")
                    try:
                        resp = await route.fetch()
                        body = await resp.body()
                        if len(body) > 50 * 1024:
                            downloaded[vid] = bytes(body)
                            print(f"  [GOT] {vid}: {len(body)/1e6:.1f}MB")
                            if len(downloaded) >= len(TARGET_VIDS):
                                download_done.set()
                        await route.fulfill(
                            status=resp.status,
                            headers=dict(resp.headers),
                            body=body,
                        )
                        return
                    except Exception as e:
                        print(f"  [ERR] route: {e}")
                        await route.continue_()
                        return
            await route.continue_()

        await page.route("**/*mpvideo*", handle_route)

        print("Navigating to article...")
        await page.goto(ARTICLE_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector("#js_content", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(3)

        title = await page.title()
        print(f"Title: {title}")
        if "验证" in title:
            print("[ERROR] CAPTCHA! Need interactive login.")
            await browser.close()
            sys.exit(1)

        # Extract video URLs and force playback
        video_urls = await page.evaluate("""
            () => {
                var urls = [];
                document.querySelectorAll('video[src]').forEach(v => urls.push(v.src));
                document.querySelectorAll('.video_iframe').forEach(el => {
                    var s = el.getAttribute('data-src');
                    if (s) urls.push(s);
                });
                return urls;
            }
        """)
        print(f"Page has {len(video_urls)} video URLs")

        # Force load videos by creating new <video> elements with the URLs
        # This triggers actual network requests through the browser
        print("Forcing video network requests...")
        for i, url in enumerate(video_urls):
            if "mpvideo.qpic.cn" not in url:
                continue
            m = re.search(r'vid=([^&]+)', url)
            vid = m.group(1) if m else f"unknown_{i}"
            if vid not in TARGET_VIDS:
                continue
            if vid in downloaded:
                continue
            print(f"  Triggering fetch for {vid}...")
            try:
                await page.evaluate("""
                    async (url) => {
                        var v = document.createElement('video');
                        v.src = url;
                        v.crossOrigin = 'anonymous';
                        v.preload = 'auto';
                        v.muted = true;
                        try { v.load(); v.play(); } catch(e) {}
                        document.body.appendChild(v);
                        await new Promise(resolve => {
                            v.oncanplay = resolve;
                            v.onerror = () => { console.log('video error'); };
                            setTimeout(resolve, 5000);
                        });
                        document.body.removeChild(v);
                    }
                """, url)
            except Exception as e:
                print(f"    trigger error: {e}")

        # Wait a bit for downloads
        await asyncio.sleep(3)

        print(f"Route-intercepted: {len(downloaded)} videos so far")

        # If route didn't catch anything, try aiohttp with Playwright cookies
        if not downloaded:
            print("\nRoute interception caught nothing.")
            print("Getting fresh cookies from browser context + trying aiohttp...")

            pw_cookies = await context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in pw_cookies}

            async with aiohttp.ClientSession(cookies=cookie_dict) as session:
                for url in video_urls:
                    if "mpvideo.qpic.cn" not in url:
                        continue
                    m = re.search(r'vid=([^&]+)', url)
                    if not m:
                        continue
                    vid = m.group(1)
                    if vid not in TARGET_VIDS:
                        continue

                    local_path = os.path.join(ARTICLE_DIR, f"video_{vid}.mp4")
                    print(f"  aiohttp GET {vid[:20]}...")
                    try:
                        async with session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=300),
                            headers={
                                "Referer": "https://mp.weixin.qq.com/",
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                            },
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                if len(data) > 50 * 1024:
                                    downloaded[vid] = data
                                    print(f"  [OK] {vid}: {len(data)/1e6:.1f}MB")
                                else:
                                    print(f"  [FAIL] Small: {len(data)}B")
                            else:
                                print(f"  [FAIL] HTTP {resp.status}")
                    except Exception as e:
                        print(f"  [FAIL] {vid}: {e}")

        await browser.close()

    print(f"\nTotal: {len(downloaded)}/{len(TARGET_VIDS)}")

    if not downloaded:
        print("\n[FAIL] All methods failed. Possible issues:")
        print("  - Cookies expired or CAPTCHA triggered")
        print("  - CDN geo-restriction / anti-bot detection")
        print("  - Auth tokens expired (try re-downloading article)")
        print("Please re-login: cd wechat-archive-tool && python main.py")
        sys.exit(1)

    for vid, data in downloaded.items():
        local_path = os.path.join(ARTICLE_DIR, f"video_{vid}.mp4")
        with open(local_path, "wb") as fh:
            fh.write(data)
        print(f"  Saved: video_{vid}.mp4 ({len(data)/1e6:.1f}MB)")

    update_html({vid: f"video_{vid}.mp4" for vid in downloaded})
    print("\nDone!")


def update_html(local_vids):
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")

    for span in soup.find_all("span", class_="video_iframe"):
        vid = span.get("vid", "") or span.get("data-mpvid", "")
        if vid not in local_vids:
            continue
        local_name = local_vids[vid]
        vw = span.get("data-vw", "")

        style = "max-width:100%;display:block;margin:12px auto;border-radius:4px;background:#000"
        if vw:
            style += f"width:{vw}px;"
        video_tag = soup.new_tag("video", controls="", preload="metadata", style=style)
        source_tag = soup.new_tag("source", src=local_name, type="video/mp4")
        video_tag.append(source_tag)

        parent = span.find_parent("section")
        if parent:
            parent.replace_with(video_tag)
        else:
            span.replace_with(video_tag)
        print(f"  Replaced {vid}")

    for vtag in soup.find_all("video"):
        if "mpvideo.qpic.cn" in vtag.get("src", ""):
            vtag.decompose()
    for el in soup.find_all(["span","div"], attrs={"data-src": True}):
        if any(d in el.get("data-src", "") for d in ["mp.weixin.qq.com","mpvideo"]):
            el["data-src"] = ""
    for el in soup.find_all(attrs={"data-cover": True}):
        if "mmbiz.qpic.cn" in el.get("data-cover", ""):
            el["data-cover"] = ""
    for meta in soup.find_all("meta", attrs={"property": "og:image"}):
        meta["content"] = "cover.jpg"
    for meta in soup.find_all("meta", attrs={"name": "twitter:image"}):
        meta["content"] = "cover.jpg"
    for meta in soup.find_all("meta", attrs={"property": "twitter:image"}):
        meta["content"] = "cover.jpg"
    for img in soup.find_all("img"):
        if "mmbiz.qpic.cn" in img.get("src", ""):
            img["src"] = ""
            print("  FIX: removed remote img")

    result = str(soup)
    result = result.replace("&amp;", "&")

    violations = re.findall(
        r'https?://(?:mpvideo\.qpic\.cn|mp\.weixin\.qq\.com/mp/|mmbiz\.qpic\.cn)[^"]*',
        result,
    )
    violations = [v for v in violations if "be4l_9rWF541w39HdrBlHA" not in v]
    if violations:
        print(f"  VIOLATIONS ({len(violations)}): {set(violations)}")
    else:
        print("  OK: no remote violations")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"  Saved ({len(result)} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
