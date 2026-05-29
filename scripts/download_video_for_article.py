"""
Download videos from WeChat CDN for the 哨兵组专访 article,
replace WeChat video player UI with simple <video> tags.
"""
import os
import re
import sys
import asyncio
import aiohttp
from bs4 import BeautifulSoup

ARTICLE_DIR = r"D:\SLDX_Ambition_Website\doc\public\wechat\articles\2023-03-29_哨兵组专访"
HTML_PATH = os.path.join(ARTICLE_DIR, "index.html")

VIDEOS = [
    {
        "vid": "wxv_2859238637077626882",
        "url": "https://mpvideo.qpic.cn/0bc3nyadaaaaiaadhtbdajsfa3wdgbxaamaa.f10002.mp4?dis_k=c4ae85482c90f17eb950c3e4fccbf0fe&dis_t=1779548903&play_scene=10120&auth_info=YL+rprc/FXw+0eGUngNeOT1uT2JiNkY9Yx57GwN6I0JdTjp8NxYOMUl0CCFkaVMZKWQ=&auth_key=1f2c79fe5da46ed304df31a55327527c&vid=wxv_2859238637077626882&format_id=10002&support_redirect=0&mmversion=false",
    },
    {
        "vid": "wxv_2859240235946311683",
        "url": "https://mpvideo.qpic.cn/0bc3ayadaaaarmadhmbdabsfabwdgadaamaa.f10002.mp4?dis_k=53da5cf5b61fe20ccabaf323fde1c678&dis_t=1779548903&play_scene=10120&auth_info=bZyQgus5Fns40LnDzwZebjpuSGQxM0BsPkh8Hgd3dRBQHm90YRUNNk91UHY1bFNOLmQ=&auth_key=4de0ea7d40002080a5d41be7a1f609f6&vid=wxv_2859240235946311683&format_id=10002&support_redirect=0&mmversion=false",
    },
]


async def download_video(session, vid, url):
    local_name = f"video_{vid}.mp4"
    local_path = os.path.join(ARTICLE_DIR, local_name)

    if os.path.exists(local_path):
        size = os.path.getsize(local_path)
        if size > 1024 * 100:  # at least 100KB
            print(f"  [SKIP] Exists: {local_name} ({size/1e6:.1f}MB)")
            return local_name
        print(f"  [WARN] Existing too small ({size}B), re-downloading...")

    print(f"  Downloading {local_name}...")
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
                if len(data) > 1024 * 100:
                    with open(local_path, "wb") as fh:
                        fh.write(data)
                    size_mb = len(data) / 1e6
                    print(f"  [OK] {local_name} ({size_mb:.1f}MB)")
                    return local_name
                else:
                    print(f"  [FAIL] Small response: {len(data)}B, HTTP {resp.status}")
                    return None
            else:
                print(f"  [FAIL] HTTP {resp.status} for {vid}")
                return None
    except asyncio.TimeoutError:
        print(f"  [FAIL] Timeout: {vid}")
        return None
    except Exception as e:
        print(f"  [FAIL] {vid}: {e}")
        return None


def cleanup_html(local_vids):
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    # Find all video_iframe spans
    for span in soup.find_all("span", class_="video_iframe"):
        mpvid = span.get("data-mpvid", "")
        vid = span.get("vid", "")

        if vid not in local_vids:
            print(f"  [WARN] Video '{vid}' not downloaded, keeping as-is")
            continue

        local_name = local_vids[vid]
        vw = span.get("data-vw", "")

        # Create simple video tag
        video_tag = soup.new_tag("video", controls="", preload="metadata",
                                 style="max-width:100%;display:block;margin:12px auto;border-radius:4px;background:#000")
        if vw:
            video_tag["style"] += f"width:{vw}px;"
        source_tag = soup.new_tag("source", src=local_name, type="video/mp4")
        video_tag.append(source_tag)

        # Find parent section and replace
        parent_section = span.find_parent("section")
        if parent_section:
            parent_section.replace_with(video_tag)
            print(f"  Replaced video_iframe ({vid}) -> {local_name}")
        else:
            # Fallback: replace the span itself
            span.replace_with(video_tag)
            print(f"  Replaced span ({vid}) -> {local_name}")

    # Remove any orphaned video elements with remote URLs
    for vtag in soup.find_all("video"):
        src = vtag.get("src", "")
        if "mpvideo.qpic.cn" in src or "mp.weixin.qq.com" in src:
            vtag.decompose()

    # Remove orphaned remote data-src attributes
    for el in soup.find_all(attrs={"data-src": True}):
        dsrc = el.get("data-src", "")
        if "mp.weixin.qq.com" in dsrc or "mpvideo.qpic.cn" in dsrc:
            el["data-src"] = ""

    # Remove data-cover with remote URLs
    for el in soup.find_all(attrs={"data-cover": True}):
        dc = el.get("data-cover", "")
        if "mmbiz.qpic.cn" in dc:
            el["data-cover"] = ""

    # Fix any remaining mmbiz.qpic.cn remote img src (shouldn't exist)
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "mmbiz.qpic.cn" in src:
            print(f"  [FIX] Replacing remote img src: {src[:80]}...")
            img["src"] = ""

    # Generate HTML string
    result = str(soup)

    # Fix BeautifulSoup amp escaping
    result = result.replace("&amp;", "&")

    # Verify
    remote_patterns = [
        r'https?://mpvideo\.qpic\.cn',
        r'https?://mp\.weixin\.qq\.com/(?!s/be4l_9rWF541w39HdrBlHA)',
    ]
    violations = []
    for pat in remote_patterns:
        m = re.findall(pat, result)
        violations.extend(m)

    og_url_found = 'https://mp.weixin.qq.com/s/be4l_9rWF541w39HdrBlHA' in result
    print(f"\n  og:url preserved: {og_url_found}")
    
    # Exclude og:url from violations
    violations = [v for v in violations if 'be4l_9rWF541w39HdrBlHA' not in v]
    
    if violations:
        print(f"  [VIOLATIONS] {len(violations)} remote references remain:")
        for v in violations[:10]:
            print(f"    - {v[:120]}...")
    else:
        print("  No remote reference violations found (excluding og:url)")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\n  Saved: {HTML_PATH} ({len(result)} bytes)")
    return len(violations) == 0


async def main():
    print("=" * 60)
    print("Video download & HTML cleanup: 哨兵组专访")
    print("=" * 60)

    connector = aiohttp.TCPConnector(limit=2, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        local_vids = {}
        for v in VIDEOS:
            result = await download_video(session, v["vid"], v["url"])
            if result:
                local_vids[v["vid"]] = result

        if not local_vids:
            print("\n[FAIL] No videos downloaded.")
            print("Auth tokens may be expired. Try re-downloading article with Playwright.")
            sys.exit(1)

        print(f"\n  Videos downloaded: {len(local_vids)}/{len(VIDEOS)}")
        cleanup_html(local_vids)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
