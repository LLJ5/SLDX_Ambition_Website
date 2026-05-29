import re
from pathlib import Path

base = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
dirs = [
    '2022-03-08_戴最可爱的发绳，造最猛的机器人！',
    '2021-05-11_欢迎宁校长莅临指导！',
    '2021-04-23_RoboMaster2021赛事简介',
    '2020-12-31_2020年终总结',
    '2020-12-25_快乐的圣诞节',
]

for d in dirs:
    ad = base / d
    html = (ad / 'index.html').read_text(encoding='utf-8')
    n = len(list(ad.iterdir()))
    has_js = 'id="js_content"' in html
    img_cdn = bool(re.search(r'https?://[^\s"<>\x27]*mmbiz\.qpic\.cn', html))
    video_cdn = 'mpvideo.qpic.cn' in html
    has_video = 'video_iframe' in html or '<video' in html
    sz = len(html) // 1024
    print(f'{d[:30]:30s} | {n:3d}f | {sz:4d}KB | js={has_js} | imgCDN={img_cdn} | vCDN={video_cdn} | video={has_video}')
