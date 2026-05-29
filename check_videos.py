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
    videos = sorted(ad.glob('video_*.mp4'))
    sizes = [f'{v.stat().st_size//1024}KB' for v in videos]
    remote = 'mpvideo.qpic.cn' in html
    print(f'{d[:30]:30s} | videos={[v.name for v in videos]} {",".join(sizes) if sizes else ""} | remote={remote}')
