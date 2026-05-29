"""Replace remote video poster URLs with local cover.jpg."""
import re
from pathlib import Path

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
TARGETS = [
    '2022-03-08_戴最可爱的发绳，造最猛的机器人！',
    '2021-05-11_欢迎宁校长莅临指导！',
    '2021-04-23_RoboMaster2021赛事简介',
    '2020-12-31_2020年终总结',
    '2020-12-25_快乐的圣诞节',
]

for d in TARGETS:
    ad = BASE / d
    html_path = ad / 'index.html'
    html = html_path.read_text(encoding='utf-8')

    # Replace video poster URLs with cover.jpg
    html, count = re.subn(
        r'poster="https?://[^"]*mmbiz\.qpic\.cn[^"]*"',
        'poster="cover.jpg"',
        html
    )
    html = re.sub(
        r'poster="https?://[^"]*mmecoa\.qpic\.cn[^"]*"',
        'poster="cover.jpg"',
        html
    )

    # Also fix og:image
    html = re.sub(r'content="[^"]*mmbiz\.qpic\.cn[^"]*"', 'content="cover.jpg"', html)
    html = re.sub(r'content="[^"]*mmecoa\.qpic\.cn[^"]*"', 'content="cover.jpg"', html)

    html_path.write_text(html, encoding='utf-8')

    remote = 'mmbiz.qpic.cn' in html or 'mmecoa.qpic.cn' in html
    print(f'{d[:45]}: poster replaced x{count}, remote={remote}')
