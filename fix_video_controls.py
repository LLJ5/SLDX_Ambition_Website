"""Fix video elements: add controls, fix preload."""
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

    # Add controls attribute to video tags that lack it
    html = re.sub(r'<video ([^>]*?)src="video_1\.mp4"', r'<video \1controls src="video_1.mp4"', html)
    # Fix preload to auto
    html = html.replace('preload="metadata"', 'preload="auto"')
    # Remove controlslist (prevents download UI)
    html = re.sub(r'\s*controlslist="[^"]*"', '', html)

    html_path.write_text(html, encoding='utf-8')
    print(f'{d[:30]}: fixed')
