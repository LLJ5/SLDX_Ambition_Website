#!/usr/bin/env python3
"""
Optimize WeChat article archive for GitHub Pages deployment.

Steps:
1. CSS Deduplication (extract shared styles)
2. Font Deduplication
3. Emoji Deduplication
4. Image compression (resize + quality, backup originals)
5. HTML minification
6. Generate metadata JSON for VitePress
"""

import os, re, hashlib, shutil, json, subprocess, urllib.request, html
from collections import defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
ARTICLES = PROJ / 'doc/public/wechat/articles'
SHARED = ARTICLES / '_shared'
BACKUP = PROJ / 'doc/public/wechat-backups'
METADATA_JSON = PROJ / 'doc/public/wechat/wechat-metadata.json'
MIN_COVERAGE = 0.8
MAX_WIDTH = 1200
JPEG_QUALITY = 75

def get_html_files():
    return sorted(ARTICLES.glob('*/index.html'))

# ─── Step 0: Download missing SVG lazy-bgimg images ──────────────────

def fix_svg_lazy_bgimg():
    """
    Some articles have SVG elements with data-lazy-bgimg pointing to
    remote WeChat CDN URLs that weren't downloaded. Download them now
    and update both data-lazy-bgimg and background-image in style.
    """
    print("Scanning for SVG lazy-bgimg images...")
    html_files = list(ARTICLES.glob('*/index.html'))
    total_downloaded = 0

    for fp in html_files:
        content = fp.read_text(encoding='utf-8')
        urls = re.findall(r'data-lazy-bgimg="(https?://[^"]*mmbiz\.qpic\.cn[^"]*)"', content)
        if not urls:
            continue

        article_dir = fp.parent
        url_to_local = {}
        changed = False

        for url in urls:
            if url in url_to_local:
                continue
            clean_url = html.unescape(url)
            base_url = clean_url.split('?')[0]
            ext = base_url.rsplit('.', 1)[-1].lower()
            if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'):
                ext = None
            try:
                req = urllib.request.Request(clean_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://mp.weixin.qq.com/',
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                    if len(data) > 500:
                        if ext is None:
                            ct = resp.headers.get('Content-Type', '')
                            if 'png' in ct:
                                ext = 'png'
                            elif 'gif' in ct:
                                ext = 'gif'
                            elif 'webp' in ct:
                                ext = 'webp'
                            elif data[:4] == b'\x89PNG':
                                ext = 'png'
                            elif data[:3] == b'GIF':
                                ext = 'gif'
                            elif data[:2] == b'\xff\xd8':
                                ext = 'jpg'
                            else:
                                ext = 'jpg'
                        local_name = f'svg_{len(list(article_dir.glob("svg_*")))+1}.{ext}'
                        local_path = article_dir / local_name
                        local_path.write_bytes(data)
                        url_to_local[url] = local_name
                        total_downloaded += 1
            except Exception:
                pass

        if not url_to_local:
            continue

        for url, local_name in url_to_local.items():
            content = content.replace(f'data-lazy-bgimg="{url}"', f'data-lazy-bgimg="{local_name}"')

        def replace_svg_bg(match):
            svg_attr = match.group(0)
            for url, local_name in url_to_local.items():
                svg_attr = svg_attr.replace(url, local_name)
            lazy_match = re.search(r'data-lazy-bgimg="([^"]+)"', svg_attr)
            local_name = lazy_match.group(1) if lazy_match else ""
            style_match = re.search(r'style="([^"]*)"', svg_attr) or re.search(r"style='([^']*)'", svg_attr)
            if style_match and local_name:
                style_val = style_match.group(1)
                if 'background-image' in style_val:
                    style_val = re.sub(r'background-image:\s*url\([^)]+\)',
                                       f'background-image: url({local_name})', style_val)
                else:
                    style_val = f'background-image: url({local_name}); background-size: cover; background-repeat: no-repeat; ' + style_val
                svg_attr = (svg_attr[:style_match.start(1)] + style_val +
                           svg_attr[style_match.end(1):])
            return svg_attr

        content = re.sub(r'<svg[^>]*data-lazy-bgimg="[^"]*"[^>]*>', replace_svg_bg, content)
        fp.write_text(content, encoding='utf-8')
        changed = True

        if changed:
            print(f"  {fp.parent.name}: downloaded {len(url_to_local)} SVG images")

    print(f"  Total: {total_downloaded} SVG images downloaded\n")




def _normalize_style_block(block):
    return re.sub(r'\s+id="[^"]*"', '', block, count=1)

def analyze_and_extract_css(html_files):
    block_counts = defaultdict(int)
    block_sample = {}
    block_originals = defaultdict(set)
    print(f"Analyzing {len(html_files)} HTML files...")
    for fp in html_files:
        html = fp.read_text(encoding='utf-8')
        blocks = re.findall(r'<style[^>]*>.*?</style>', html, re.DOTALL)
        seen_norm = set()
        for b in blocks:
            nb = _normalize_style_block(b)
            nh = hashlib.md5(nb.encode()).hexdigest()
            if nh not in seen_norm:
                block_counts[nh] += 1
                if nh not in block_sample:
                    block_sample[nh] = nb
                block_originals[nh].add(b)
                seen_norm.add(nh)
    threshold = int(len(html_files) * MIN_COVERAGE)
    common = sorted(
        [(h, cnt, block_sample[h]) for h, cnt in block_counts.items() if cnt >= threshold],
        key=lambda x: -len(x[2])
    )
    print(f"Found {len(common)} common CSS blocks (≥{threshold}/{len(html_files)} files)")
    SHARED.mkdir(parents=True, exist_ok=True)
    css_map = {}
    for idx, (h, cnt, block) in enumerate(common):
        inner = re.sub(r'</?style[^>]*>', '', block).strip()
        fname = f's{idx:03d}.css'
        (SHARED / fname).write_text(inner, encoding='utf-8')
        css_map[h] = fname
        print(f"  {fname}: {len(inner):,} bytes ({cnt} files)")
    block_map = {h: block_sample[h] for h, cnt, _ in common}
    return css_map, block_map, block_originals

def rewrite_html(html_files, css_map, block_originals):
    print("Rewriting HTML files...")
    saved = 0
    for i, fp in enumerate(html_files):
        html = fp.read_text(encoding='utf-8')
        orig = len(html)
        for h in css_map:
            for original in block_originals.get(h, []):
                if original in html:
                    html = html.replace(original, f'<link rel="stylesheet" href="../_shared/{css_map[h]}">')
                    break
        if orig != len(html):
            fp.write_text(html, encoding='utf-8')
            saved += orig - len(html)
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(html_files)}...")
    print(f"  Done. Saved {saved / 1e6:.1f} MB")

# ─── Step 2: Font Deduplication ──────────────────────────────────────

def dedup_fonts(html_files):
    ttf_files = list(ARTICLES.glob('*/font_*.ttf'))
    if not ttf_files:
        return
    font_dir = SHARED / 'fonts'
    font_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ttf_files[0], font_dir / 'wechat.ttf')
    for fp in html_files:
        rel = os.path.relpath(str(font_dir), str(fp.parent))
        html = fp.read_text(encoding='utf-8')
        html = re.sub(r'url\([^)]*\.ttf\)', f'url({rel}/wechat.ttf)', html)
        fp.write_text(html, encoding='utf-8')
    for fp in ttf_files:
        if fp.parent != font_dir:
            fp.unlink()
    print(f"Deduplicated {len(ttf_files)} fonts → 1 shared")

# ─── Step 3: Emoji Deduplication ─────────────────────────────────────

def dedup_emojis():
    emoji_map = {}
    removed = 0
    for fp in sorted(ARTICLES.glob('*/emoji_*.png')):
        content = fp.read_bytes()
        h = hashlib.md5(content).hexdigest()
        if h in emoji_map:
            fp.unlink()
            removed += 1
        else:
            emoji_map[h] = fp
    print(f"Removed {removed} duplicate emoji PNGs, kept {len(emoji_map)} unique")

# ─── Step 4: Image Compression ───────────────────────────────────────

def _compress_one(args):
    """Compress a single image file. Returns (before, after, action)."""
    fp, = args
    from PIL import Image
    size_before = fp.stat().st_size
    if size_before < 5120:
        return (size_before, size_before, 'skip')

    try:
        img = Image.open(fp)
        w, h = img.size
        if w > MAX_WIDTH:
            ratio = MAX_WIDTH / w
            img = img.resize((MAX_WIDTH, int(h * ratio)), Image.LANCZOS)

        ext = fp.suffix.lower()
        if ext in ('.jpg', '.jpeg'):
            if img.mode in ('RGBA', 'P', 'CMYK'):
                img = img.convert('RGB')
            img.save(str(fp), 'JPEG', quality=JPEG_QUALITY, optimize=True)
        elif ext == '.png':
            img.save(str(fp), 'PNG', optimize=True)
        else:
            return (size_before, size_before, 'skip')

        size_after = fp.stat().st_size
        return (size_before, size_after, 'ok')
    except Exception as e:
        return (size_before, size_before, f'err: {e}')

def compress_images():
    """Resize large images, compress JPEGs, backup originals using multiprocessing."""
    image_files = []
    for pat in ('*/cover.*', '*/img_*.*', '*/bg_*.*', '*/svg_*.*', '*/rm_*.*', '*/poster_*.*'):
        image_files.extend(ARTICLES.glob(pat))
    if not image_files:
        return

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not available, trying jpegoptim fallback...")
        try:
            subprocess.run(['jpegoptim', '--version'], capture_output=True)
            jpegs = [f for f in image_files if f.suffix.lower() in ('.jpg', '.jpeg')]
            for fp in jpegs:
                subprocess.run(['jpegoptim', '--strip-all', '--max=85', str(fp)],
                              capture_output=True, timeout=10)
            print(f"  Compressed {len(jpegs)} JPEGs with jpegoptim")
            return
        except (FileNotFoundError, Exception):
            print("Neither Pillow nor jpegoptim available, skipping image compression")
            return

    print(f"Compressing {len(image_files)} images with Pillow...")

    # Backup originals first
    BACKUP.mkdir(parents=True, exist_ok=True)
    img_backup = BACKUP / 'images'
    img_backup.mkdir(parents=True, exist_ok=True)
    for fp in image_files:
        rel_path = fp.relative_to(ARTICLES)
        backup_path = img_backup / rel_path
        if not backup_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(fp), str(backup_path))

    # Compress with multiprocessing
    try:
        from multiprocessing import Pool
        with Pool() as pool:
            results = pool.map(_compress_one, [(fp,) for fp in image_files])
    except Exception as ex:
        print(f"  Multiprocessing failed ({ex}), falling back to serial...")
        results = [_compress_one((fp,)) for fp in image_files]

    total_before = sum(r[0] for r in results)
    total_after = sum(r[1] for r in results)
    compressed = sum(1 for r in results if r[2] == 'ok')
    skipped = sum(1 for r in results if r[2] == 'skip')
    errors = sum(1 for r in results if r[2].startswith('err'))

    reduction = total_before - total_after
    print(f"  Compressed {compressed} images, skipped {skipped}, errors {errors}")
    print(f"  Before: {total_before / 1e6:.1f} MB → After: {total_after / 1e6:.1f} MB")
    print(f"  Saved: {reduction / 1e6:.1f} MB ({100 * reduction / max(total_before, 1):.1f}%)")
    print(f"  Originals backed up to: {img_backup}")

# ─── Step 5: HTML Minification ───────────────────────────────────────

def minify_html():
    """Remove excessive whitespace from HTML files."""
    print("Minifying HTML...")
    saved = 0
    html_files = list(ARTICLES.glob('*/index.html'))
    for fp in html_files:
        html = fp.read_text(encoding='utf-8')
        orig = len(html)
        # Collapse multiple whitespace (but not in <pre> or <code>)
        parts = re.split(r'(<pre[^>]*>.*?</pre>|<code[^>]*>.*?</code>)', html, flags=re.DOTALL)
        result = []
        for part in parts:
            if part.startswith('<pre') or part.startswith('<code'):
                result.append(part)
            else:
                part = re.sub(r'\n\s*\n', '\n', part)
                part = re.sub(r'>\s+<', '><', part)
                result.append(part)
        html = ''.join(result)
        fp.write_text(html, encoding='utf-8')
        saved += orig - len(html)
    print(f"  Saved {saved / 1e6:.1f} MB")

# ─── Step 6: Generate Metadata JSON ──────────────────────────────────

def generate_metadata():
    """Generate metadata JSON for VitePress data loader."""
    print("Generating metadata...")
    SKIP = ['2026-05-22_公众号运营回归个人通知', '2025-09-15_我们搬家啦', '2025-06-03_沈理电协Ambition战队官网发布', '2025-06-18_大疆_2026_校招', '2024-06-13_大疆_2025', '2024-07-04_DJI_大疆', '2024-07-07_测一测你来_DJI', '2022-04-25_下一场，去大疆', '2018-04-13_DJI大疆创新RoboMaster机器人夏令营', '2018-03-09_RoboMaster2018最全招聘', '2025-03-06_机甲大师十周年徽章，即将发布', '2015-10-01_沈阳周边竟隐藏了十个小众旅游天堂！美得窒息！十一走起！']
    PROTECTED = ['2024-12-15_冬日畅言___RM线下交流会', '2025-05-31_战队总结视频']
    articles = []
    for entry_dir in sorted(ARTICLES.iterdir()):
        if not entry_dir.is_dir() or entry_dir.name.startswith('_'):
            continue
        if any(entry_dir.name.startswith(s) for s in SKIP):
            continue
        title_part = entry_dir.name[11:]
        if title_part.startswith('转载') or title_part.startswith('转载_'):
            continue
        if any(entry_dir.name.startswith(s) for s in SKIP):
            continue
        m = re.match(r'^(\d{4}-\d{2}-\d{2})_(.*)', entry_dir.name)
        if not m:
            continue
        date_str, _ = m.groups()
        html_path = entry_dir / 'index.html'
        title = entry_dir.name[11:].replace('_', ' ')
        if html_path.exists():
            content = html_path.read_text(encoding='utf-8')
            tm = re.search(r'<title>(.*?)</title>', content)
            if tm:
                title = html.unescape(tm.group(1).strip())

        has_cover = False
        cover_ext = None
        for ext in ('jpg', 'png', 'webp'):
            if (entry_dir / f'cover.{ext}').exists():
                has_cover = True
                cover_ext = ext
                break

        has_video = False
        if html_path.exists() and content:
            has_video = bool(re.search(r'<video\b|<mpvideo\b|video_\w+\.mp4|v\.qq\.com|bilibili\.com/player', content))

        articles.append({
            'date': date_str,
            'year': int(date_str[:4]),
            'title': title,
            'dir': entry_dir.name,
            'hasCover': has_cover,
            'coverExt': cover_ext,
            'hasVideo': has_video
        })

    articles.sort(key=lambda a: a['date'], reverse=True)
    METADATA_JSON.write_text(json.dumps(articles, ensure_ascii=False), encoding='utf-8')
    print(f"  Generated metadata for {len(articles)} articles → {METADATA_JSON}")
    return articles

# ─── Stats ───────────────────────────────────────────────────────────

def show_stats():
    total = sum(f.stat().st_size for f in ARTICLES.rglob('*') if f.is_file())
    print(f"\nFinal articles size: {total / 1e6:.1f} MB")

# ─── Main ────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("WeChat Article Archive Optimizer")
    print("=" * 60)

    html_files = get_html_files()
    print(f"\nFound {len(html_files)} article HTML files\n")

    # Step 0: Fix SVG lazy-bgimg
    print("[0/6] Fix SVG lazy-bgimg Images")
    fix_svg_lazy_bgimg()

    # Step 1: CSS Dedup
    print("[1/6] CSS Deduplication")
    css_map, block_content, block_originals = analyze_and_extract_css(html_files)
    rewrite_html(html_files, css_map, block_originals)

    # Step 2: Font Dedup
    print("\n[2/6] Font Deduplication")
    dedup_fonts(html_files)

    # Step 3: Emoji Dedup
    print("\n[3/6] Emoji Deduplication")
    dedup_emojis()

    # Step 4: Image Compression
    print("\n[4/6] Image Compression")
    compress_images()

    # Step 5: HTML Minification
    print("\n[5/6] HTML Minification")
    minify_html()

    # Step 6: Metadata
    print("\n[6/6] Generate Metadata")
    generate_metadata()

    print("\n" + "=" * 60)
    show_stats()

if __name__ == '__main__':
    main()
