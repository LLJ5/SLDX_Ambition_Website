import re
from pathlib import Path

# Fix article 4: replace remote video src with local
ad = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles\2020-12-31_2020年终总结')
html = (ad / 'index.html').read_text(encoding='utf-8')
html = re.sub(r'src="https?://mpvideo\.qpic\.cn/[^"]*"', 'src="video_1.mp4"', html)
(ad / 'index.html').write_text(html, encoding='utf-8')
print(f'Article 4 fixed: remote={"mpvideo.qpic.cn" in html}')

# Also check article 5 (should be fine)
ad5 = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles\2020-12-25_快乐的圣诞节')
h5 = (ad5 / 'index.html').read_text(encoding='utf-8')
r5 = 'mpvideo.qpic.cn' in h5
print(f'Article 5: remote={r5}')
