"""Check current state and find og:url for article 5."""
from pathlib import Path
import re

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

# Check the 5th article
for d in BASE.iterdir():
    if d.is_dir() and d.name.startswith('2020-12-25'):
        html = (d / 'index.html').read_text(encoding='utf-8')
        m = re.search(r'property="og:url"\s+content="([^"]*)"', html)
        url = m.group(1) if m else 'NOT FOUND'
        m2 = re.search(r'property="og:title"\s+content="([^"]*)"', html)
        title = m2.group(1) if m2 else 'N/A'
        print(f'Dir: {d.name}')
        print(f'og:url: {url}')
        print(f'og:title: {title}')
        print(f'Files: {len(list(d.iterdir()))}')
        print(f'Has video_iframe: {"video_iframe" in html}')
        print(f'Size: {len(html)}B')
