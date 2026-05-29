"""Simplify video structure: unwrap WeChat player containers."""
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

    # Find the outermost video player containers and replace them
    for container in soup.find_all('div', class_='mp-video-player'):
        video = container.find('video')
        if not video:
            continue
        src = video.get('src', '')
        if 'video_1.mp4' not in src:
            continue

        new_video = soup.new_tag('video')
        new_video['src'] = src
        new_video['controls'] = ''
        new_video['preload'] = 'auto'
        new_video['poster'] = 'cover.jpg'
        new_video['style'] = 'max-width:100%;width:100%;height:auto;display:block'
        container.replace_with(new_video)
        print(f'  {d[:30]}: replaced mp-video-player')

    # Also check for js_mpvedio wrappers (alt class name)
    for container in soup.find_all('div', id=re.compile(r'^js_mpvedio_')):
        video = container.find('video')
        if not video:
            continue
        src = video.get('src', '')
        if 'video_1.mp4' not in src:
            continue

        new_video = soup.new_tag('video')
        new_video['src'] = src
        new_video['controls'] = ''
        new_video['preload'] = 'auto'
        new_video['poster'] = 'cover.jpg'
        new_video['style'] = 'max-width:100%;width:100%;height:auto;display:block'
        container.replace_with(new_video)
        print(f'  {d[:30]}: replaced js_mpvedio')

    # Check for page_video_wrapper
    for container in soup.find_all('div', class_='page_video_wrapper'):
        video = container.find('video')
        if not video:
            continue
        src = video.get('src', '')
        if 'video_1.mp4' not in src:
            continue

        new_video = soup.new_tag('video')
        new_video['src'] = src
        new_video['controls'] = ''
        new_video['preload'] = 'auto'
        new_video['poster'] = 'cover.jpg'
        new_video['style'] = 'max-width:100%;width:100%;height:auto;display:block'
        container.replace_with(new_video)
        print(f'  {d[:30]}: replaced page_video_wrapper')

    # Final fallback: find any video that's still wrapped deep, unwrap it
    for video in list(soup.find_all('video')):
        src = video.get('src', '')
        if 'video_1.mp4' not in src:
            continue
        # Check if parent chain still has wrapper classes
        p = video.parent
        needs_fix = False
        for _ in range(8):
            if not p or p.name == 'body':
                break
            classes = p.get('class', [])
            if any(c in ('js_video_poster', 'js_page_video', 'page_video') for c in classes):
                needs_fix = True
                break
            p = p.parent
        if needs_fix:
            print(f'  {d[:30]}: unwrapping deep video')
            video_copy = soup.new_tag('video')
            video_copy['src'] = src
            video_copy['controls'] = ''
            video_copy['preload'] = 'auto'
            video_copy['poster'] = 'cover.jpg'
            video_copy['style'] = 'max-width:100%;width:100%;height:auto;display:block'
            video.replace_with(video_copy)

    result = str(soup)
    result = result.replace('&amp;', '&')
    html_path.write_text(result, encoding='utf-8')

print('Done simplifying video structures.')
