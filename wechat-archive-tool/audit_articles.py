#!/usr/bin/env python3
"""Audit article directories for common issues (read-only, no modifications)."""

import os
import re
from pathlib import Path
from datetime import date

ARTICLES_DIR = Path(r"D:\SLDX_Ambition_Website\doc\public\wechat\articles")
CUTOFF_DATE = date(2023, 3, 23)

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}


def parse_date_from_dirname(dirname):
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})_', dirname)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def get_article_dirs():
    dirs = []
    for entry in sorted(ARTICLES_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith('_'):
            continue
        d = parse_date_from_dirname(entry.name)
        if d and d < CUTOFF_DATE:
            dirs.append(entry)
    return dirs


def check_cdn_refs(html):
    cnt = 0
    cnt += len(re.findall(r'mmbiz\.qpic\.cn', html))
    cnt += len(re.findall(r'mmecoa\.qpic\.cn', html))
    return cnt


def check_og_image_remote(html):
    # property="og:image" ... content="..."
    m = re.search(r'property="og:image"[^>]*?content="([^"]*)"', html)
    if not m:
        # content="..." ... property="og:image"
        m = re.search(r'content="([^"]*)"[^>]*?property="og:image"', html)
    if m:
        url = m.group(1)
        if 'mmbiz.qpic.cn' in url or 'mmecoa.qpic.cn' in url:
            return url
    return None


def check_placeholder_classes(html):
    js = len(re.findall(r'js_img_placeholder', html))
    wx = len(re.findall(r'wx_img_placeholder', html))
    wxbc = len(re.findall(r'wx_imgbc_placeholder', html))
    return js, wx, wxbc


def check_data_lazy_bgimg(html):
    return len(re.findall(r'data-lazy-bgimg', html))


def check_image_mismatch(html, dir_path):
    files = set()
    for f in dir_path.iterdir():
        if f.is_file() and f.suffix.lower() in IMG_EXTS:
            files.add(f.name)

    img_srcs = re.findall(r'<img[^>]+src="([^"]*)"', html)
    mismatch = 0
    for src in img_srcs:
        if src.startswith(('http://', 'https://', '//', 'data:')):
            continue
        basename = os.path.basename(src)
        if basename and basename not in files:
            mismatch += 1
    return mismatch


def check_doctype(html):
    return len(re.findall(r'<!DOCTYPE', html, re.IGNORECASE))


def main():
    dirs = get_article_dirs()
    print(f"Found {len(dirs)} article directories with dates before {CUTOFF_DATE}")
    print("=" * 80)

    results = {}

    cdn_refs_list = []
    og_remote_list = []
    placeholder_list = []
    lazy_bgimg_list = []
    img_mismatch_list = []
    double_doctype_list = []

    for i, dir_path in enumerate(dirs):
        html_path = dir_path / 'index.html'
        if not html_path.exists():
            print(f"  WARNING: {dir_path.name} has no index.html")
            continue

        try:
            html = html_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print(f"  ERROR: {dir_path.name}: {e}")
            continue

        stats = {}

        cdn = check_cdn_refs(html)
        stats['cdn_refs'] = cdn
        if cdn > 0:
            cdn_refs_list.append((dir_path.name, cdn))

        og_remote = check_og_image_remote(html)
        stats['og_remote'] = og_remote is not None
        if og_remote:
            og_remote_list.append((dir_path.name, og_remote))

        js, wx, wxbc = check_placeholder_classes(html)
        total_ph = js + wx + wxbc
        stats['placeholders'] = total_ph
        stats['placeholders_detail'] = (js, wx, wxbc)
        if total_ph > 0:
            placeholder_list.append((dir_path.name, total_ph, js, wx, wxbc))

        lazy = check_data_lazy_bgimg(html)
        stats['data_lazy_bgimg'] = lazy
        if lazy > 0:
            lazy_bgimg_list.append((dir_path.name, lazy))

        mismatch = check_image_mismatch(html, dir_path)
        stats['img_mismatch'] = mismatch
        if mismatch > 0:
            img_mismatch_list.append((dir_path.name, mismatch))

        dc = check_doctype(html)
        stats['doctype_count'] = dc
        if dc > 1:
            double_doctype_list.append((dir_path.name, dc))

        results[dir_path.name] = stats

        if (i + 1) % 200 == 0:
            print(f"  Processed {i + 1}/{len(dirs)}...")

    print(f"\nProcessed {len(results)} article directories.\n")

    total = len(results)
    with_cdn = sum(1 for s in results.values() if s['cdn_refs'] > 0)
    with_og_remote = sum(1 for s in results.values() if s['og_remote'])
    with_ph = sum(1 for s in results.values() if s['placeholders'] > 0)
    with_lazy = sum(1 for s in results.values() if s['data_lazy_bgimg'] > 0)
    with_mm = sum(1 for s in results.values() if s['img_mismatch'] > 0)
    with_dd = sum(1 for s in results.values() if s['doctype_count'] > 1)

    total_cdn = sum(s['cdn_refs'] for s in results.values())
    total_ph = sum(s['placeholders'] for s in results.values())
    total_lazy = sum(s['data_lazy_bgimg'] for s in results.values())
    total_mm = sum(s['img_mismatch'] for s in results.values())

    pct = lambda n: f"{n * 100 // total}%" if total else "N/A"

    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print(f"  Total articles audited:               {total}")
    print(f"  With remote CDN refs:                 {with_cdn} ({pct(with_cdn)})")
    print(f"    Total CDN refs found:               {total_cdn}")
    print(f"  With og:image remote CDN URL:         {with_og_remote} ({pct(with_og_remote)})")
    print(f"  With placeholder classes:             {with_ph} ({pct(with_ph)})")
    print(f"    Total placeholder instances:        {total_ph}")
    print(f"  With data-lazy-bgimg:                 {with_lazy} ({pct(with_lazy)})")
    print(f"    Total data-lazy-bgimg instances:    {total_lazy}")
    print(f"  With image src mismatches:            {with_mm} ({pct(with_mm)})")
    print(f"    Total mismatched img refs:          {total_mm}")
    print(f"  With double DOCTYPE:                  {with_dd} ({pct(with_dd)})")

    def print_top10(title, data, fmt_fn=None):
        print(f"\n{'─' * 80}")
        print(f"Top 10: {title}")
        print(f"{'─' * 80}")
        data_sorted = sorted(data, key=lambda x: x[1], reverse=True)[:10]
        if not data_sorted:
            print("  (none)")
            return
        for i, item in enumerate(data_sorted, 1):
            if fmt_fn:
                print(f"  {i:2d}. [{item[0]}] {fmt_fn(item)}")
            else:
                print(f"  {i:2d}. [{item[0]}] count={item[1]}")

    print_top10("Remote CDN References", cdn_refs_list)
    print_top10("og:image Remote URL", og_remote_list, lambda x: x[1])
    print_top10("Placeholder Classes (js_img_placeholder / wx_img_placeholder / wx_imgbc_placeholder)",
                placeholder_list,
                lambda x: f"total={x[1]}  (js={x[2]}, wx={x[3]}, wxbc={x[4]})")
    print_top10("data-lazy-bgimg Elements", lazy_bgimg_list)
    print_top10("Image src Mismatches", img_mismatch_list)
    print_top10("Double DOCTYPE", double_doctype_list,
                lambda x: f"{x[1]} DOCTYPE declarations")

    print("\nDone.")


if __name__ == '__main__':
    main()
