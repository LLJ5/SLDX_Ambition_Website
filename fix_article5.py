"""Apply appmsg template to article 5 (2020-12-25)."""
import re
from pathlib import Path

BASE = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
ARTICLE_DIR = BASE / '2020-12-25_快乐的圣诞节'
REF_APPMSG_PREFIX = '2024-12-15_冬日畅言'

html_path = ARTICLE_DIR / 'index.html'
html = html_path.read_text(encoding='utf-8')

ref_dir = next(BASE.glob(REF_APPMSG_PREFIX + '*'))
ref_html = (ref_dir / 'index.html').read_text(encoding='utf-8')
ref_head = ref_html[:ref_html.find('</head>')]

body_start = html.find('<body')
head = html[:body_start]
body = html[body_start:]
body_tag_end = body.find('>') + 1
body_tag = body[:body_tag_end]
body_content = body[body_tag_end:]

new_head = ref_head

meta_patterns = [
    (r'<title>(.*?)</title>', None),
    (r'property="og:title"\s+content="([^"]*)"', None),
    (r'property="og:url"\s+content="([^"]*)"', None),
    (r'property="og:image"\s+content="([^"]*)"', None),
    (r'name="twitter:image"\s+content="([^"]*)"', None),
    (r'name="description"\s+content="([^"]*)"', None),
    (r'property="og:description"\s+content="([^"]*)"', None),
    (r'name="twitter:description"\s+content="([^"]*)"', None),
    (r'name="author"\s+content="([^"]*)"', None),
    (r'property="og:article:author"\s+content="([^"]*)"', None),
    (r'name="twitter:title"\s+content="([^"]*)"', None),
    (r'name="twitter:creator"\s+content="([^"]*)"', None),
]

for pattern, _ in meta_patterns:
    old_m = re.search(pattern, head)
    new_m = re.search(pattern, new_head)
    if old_m and new_m and old_m.group(1) != new_m.group(1):
        new_head = new_head.replace(new_m.group(1), old_m.group(1))

old_title = re.search(r'<title>(.*?)</title>', head)
new_title = re.search(r'<title>(.*?)</title>', new_head)
if old_title and new_title and old_title.group(1) != new_title.group(1):
    new_head = new_head.replace(new_title.group(0), old_title.group(0))

result = '<!DOCTYPE html>\n' + new_head + '</head>\n' + body_tag + body_content

if result.count('<!DOCTYPE html>') > 1:
    result = result.replace('<!DOCTYPE html>', '', 1)
if '<!DOCTYPE' in result and not result.startswith('<!DOCTYPE'):
    doctype_pos = result.find('<!DOCTYPE')
    result = result[doctype_pos:]

# Fix any CDN og:image
result = re.sub(r'content="[^"]*mmbiz\.qpic\.cn[^"]*"', 'content="cover.jpg"', result)
result = re.sub(r'content="[^"]*mmecoa\.qpic\.cn[^"]*"', 'content="cover.jpg"', result)

html_path.write_text(result, encoding='utf-8')
print(f'Size: {len(result)}B ({len(result)//1024}KB)')
print(f'Remote mmbiz: {"mmbiz.qpic.cn" in result}')
print(f'Remote mmecoa: {"mmecoa.qpic.cn" in result}')
print(f'Done: {ARTICLE_DIR.name}')
