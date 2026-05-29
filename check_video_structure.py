"""Check video element structure in all 5 articles."""
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
    html = (ad / 'index.html').read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')

    for v in soup.find_all('video'):
        src = v.get('src', '')
        controls = 'controls' in v.attrs
        preload = v.get('preload', 'none')
        style = v.get('style', '')[:80]
        # Check parent chain for hidden elements
        parent_chain = []
        p = v.parent
        for _ in range(5):
            if p and p.name:
                pid = p.get('id', '')
                pclass = ' '.join(p.get('class', []))[:50]
                pstyle = (p.get('style', '') or '')[:50]
                parent_chain.append(f'{p.name}#{pid}.{pclass} style={pstyle}')
                p = p.parent
            else:
                break

        print(f'\n=== {d[:30]} ===')
        print(f'  src={src}')
        print(f'  controls={controls} preload={preload}')
        print(f'  style={style}')
        print(f'  parents: {" -> ".join(parent_chain)}')
        break
