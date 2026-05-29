"""Replace video_iframe container spans with direct video elements."""
import re
from pathlib import Path
from bs4 import BeautifulSoup

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
DIRS = [
    '2022-03-08_戴最可爱的发绳，造最猛的机器人！',
    '2021-05-11_欢迎宁校长莅临指导！',
    '2021-04-23_RoboMaster2021赛事简介',
    '2020-12-31_2020年终总结',
    '2020-12-25_快乐的圣诞节',
]

for d in DIRS:
    ad = BASE / d
    html_path = ad / 'index.html'
    html = html_path.read_text(encoding='utf-8')

    soup = BeautifulSoup(html, 'lxml')

    # Find video elements inside video_iframe spans
    for span in soup.find_all('span', id=re.compile(r'js_mp_video_container')):
        video = span.find('video')
        if not video:
            continue
        src = video.get('src', '')
        if 'video_1.mp4' not in src:
            continue

        # Replace the span with a clean video element
        new_video = soup.new_tag('video')
        new_video['src'] = src
        new_video['controls'] = ''
        new_video['preload'] = 'metadata'
        new_video['poster'] = 'cover.jpg'
        new_video['style'] = 'max-width:100%;width:100%;height:auto;display:block'
        span.replace_with(new_video)
        print(f'  {d[:30]}: replaced video_iframe span')

    result = str(soup)
    result = result.replace('&amp;', '&')
    html_path.write_text(result, encoding='utf-8')

print('Done')
