"""Fix video height: add aspect-ratio to prevent layout shift."""
import re
from pathlib import Path

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

    # Replace video style: add aspect-ratio, background, remove height:auto
    old = 'max-width:100%;width:100%;height:auto;display:block'
    new = 'max-width:100%;width:100%;min-height:200px;display:block;background:#000'
    html = html.replace(old, new)

    html_path.write_text(html, encoding='utf-8')
    print(f'{d[:30]}: fixed aspect-ratio')

print('Done')
