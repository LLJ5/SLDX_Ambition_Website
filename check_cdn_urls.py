import re
from pathlib import Path

for d in Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles').iterdir():
    if not d.is_dir() or not d.name.startswith(('2022-03-08_', '2021-05-11_', '2021-04-23_', '2020-12-31_', '2020-12-25_')):
        continue
    html = (d / 'index.html').read_text(encoding='utf-8')
    matches = list(re.finditer(r'https?://[^\s"\'<>]*mmbiz\.qpic\.cn[^\s"\'<>]*', html))
    matches += list(re.finditer(r'https?://[^\s"\'<>]*mmecoa\.qpic\.cn[^\s"\'<>]*', html))
    if matches:
        print(f'\n{d.name}: {len(matches)} remote URLs')
        for m in matches[:3]:
            ctx_start = max(0, m.start()-60)
            ctx_end = min(len(html), m.end()+60)
            ctx = html[ctx_start:ctx_end].replace('\n', ' ')
            print(f'  pos={m.start()}: ...{ctx}...')
    else:
        print(f'{d.name}: CLEAN')
