"""Check video structure of 2022-03-01 article."""
from pathlib import Path
from bs4 import BeautifulSoup
import re

ad = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles\2022-03-01_久等！RoboMaster_机甲大师_2021_赛季纪录预告片正式上线')
html = (ad / 'index.html').read_text(encoding='utf-8')

print(f'Files: {len(list(ad.iterdir()))}')
print(f'Size: {len(html)}B')

soup = BeautifulSoup(html, 'lxml')

# Check for video elements
for v in soup.find_all('video'):
    src = v.get('src', '')
    style = v.get('style', '')[:100]
    controls = 'controls' in v.attrs
    print(f'\nVideo: src={src}')
    print(f'  controls={controls}')
    print(f'  style={style}')
    p = v.parent
    for _ in range(5):
        if p and p.name:
            pid = p.get('id', '')
            pclass = ' '.join(p.get('class', []))[:60]
            pstyle = (p.get('style', '') or '')[:80]
            print(f'  parent: {p.name}#{pid}.{pclass} style={pstyle}')
            p = p.parent

# Check iframes
for ifr in soup.find_all('iframe'):
    src = ifr.get('src', '')[:100]
    print(f'\nIframe: src={src}')

# Check video_iframe spans
for vf in soup.find_all('span', class_='video_iframe'):
    ds = vf.get('data-src', '')[:100]
    print(f'\nvideo_iframe: data-src={ds}')

# Check for remote references
remote = 'mmbiz.qpic.cn' in html or 'mpvideo.qpic.cn' in html
print(f'\nRemote refs: {remote}')

# Video files
for vf in ad.glob('video_*'):
    print(f'Video file: {vf.name} ({vf.stat().st_size//1024}KB)')

# Check mp-common-videosnap
for snap in soup.find_all('mp-common-videosnap'):
    print(f'\nmp-common-videosnap: data-url={snap.get("data-url", "")[:100]}')
