"""
Fix video HTML for all articles with videos: replace remote video elements with local <video> tags.
"""
import re
from pathlib import Path
from bs4 import BeautifulSoup

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

TARGETS = [
    '2023-03-29', '2023-03-27', '2023-03-17',
    '2022-03-08', '2021-05-11', '2021-05-05',
    '2021-04-23', '2020-12-31', '2020-12-25',
]

for target in TARGETS:
    ads = [x for x in BASE.iterdir() if x.is_dir() and x.name.startswith(target)]
    if not ads:
        print(f'{target}: NOT FOUND')
        continue
    ad = ads[0]
    h = (ad/'index.html').read_text('utf-8', errors='ignore')
    soup = BeautifulSoup(h, 'lxml')
    
    viframes = soup.find_all('span', class_='video_iframe')
    snaps = soup.find_all('mp-common-videosnap')
    local_videos = sorted(ad.glob('video_*.mp4')) + sorted(ad.glob('video_wxv_*.mp4'))
    local_names = [f.name for f in local_videos]
    has_video_tag = bool(soup.find_all('video'))
    
    remote_count = len(viframes) + len(snaps)
    
    print(f'{ad.name[:50]}')
    print(f'  video_iframe: {len(viframes)}  videosnap: {len(snaps)}  local: {len(local_videos)}  <video>tag: {has_video_tag}')
    
    if has_video_tag and remote_count == 0:
        print(f'  Already OK')
        continue
    
    if remote_count == 0:
        print(f'  No remote video elements')
        continue
    
    # Replace remote video elements with local <video> tags
    all_local = sorted(local_names)
    v_idx = 0
    
    for snap in soup.find_all('mp-common-videosnap'):
        if v_idx < len(all_local):
            tag = soup.new_tag('video')
            tag['src'] = all_local[v_idx]
            tag['controls'] = ''
            tag['style'] = 'max-width:100%;width:100%'
            snap.replace_with(tag)
            v_idx += 1
    
    for vf in soup.find_all('span', class_='video_iframe'):
        if v_idx < len(all_local):
            tag = soup.new_tag('video')
            tag['src'] = all_local[v_idx]
            tag['controls'] = ''
            tag['style'] = 'max-width:100%;width:100%'
            vf.replace_with(tag)
            v_idx += 1
    
    # Remove orphaned <video> tags with no valid local src
    orphan_count = 0
    for v in soup.find_all('video'):
        src = v.get('src', '')
        if not src or not (ad / src).exists():
            v.decompose()
            orphan_count += 1
    if orphan_count:
        result = str(soup)
        result = result.replace('&amp;', '&')
        (ad/'index.html').write_text(result, 'utf-8')
        print(f'  -> Removed {orphan_count} orphaned <video> tags')
    else:
        print(f'  -> No local files to use ({len(all_local)} local, {remote_count} remote)')
