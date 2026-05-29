"""Fix articles misidentified as share_content_page by applying appmsg template."""
import re
from pathlib import Path

BASE = Path('../doc/public/wechat/articles')
REF_APPMSG_PREFIX = '2024-12-15_冬日畅言'

def apply_appmsg_template(article_dir):
    html_path = article_dir / 'index.html'
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

    # Replace metadata from original into template head
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

    # Special handling: replace entire title tag
    old_title = re.search(r'<title>(.*?)</title>', head)
    new_title = re.search(r'<title>(.*?)</title>', new_head)
    if old_title and new_title and old_title.group(1) != new_title.group(1):
        new_head = new_head.replace(new_title.group(0), old_title.group(0))

    result = '<!DOCTYPE html>\n' + new_head + '</head>\n' + body_tag + body_content

    # Fix double DOCTYPE from template head already containing DOCTYPE
    if result.count('<!DOCTYPE html>') > 1:
        result = result.replace('<!DOCTYPE html>', '', 1)

    # If no DOCTYPE left, re-add it at start
    if '<!DOCTYPE' in result:
        doctype_pos = result.find('<!DOCTYPE')
        if doctype_pos > 0:
            result = result[doctype_pos:]
    if not result.startswith('<!DOCTYPE html>'):
        result = '<!DOCTYPE html>\n' + result

    # Fix remaining CDN og:image
    result = re.sub(r'content="[^"]*mmbiz\.qpic\.cn[^"]*"\s+property="og:image"',
                    'content="cover.jpg" property="og:image"', result)
    result = re.sub(r'property="og:image"\s+content="[^"]*mmbiz\.qpic\.cn[^"]*"',
                    'property="og:image" content="cover.jpg"', result)
    result = re.sub(r'content="[^"]*mmecoa\.qpic\.cn[^"]*"\s+property="og:image"',
                    'content="cover.jpg" property="og:image"', result)
    result = re.sub(r'property="og:image"\s+content="[^"]*mmecoa\.qpic\.cn[^"]*"',
                    'property="og:image" content="cover.jpg"', result)

    html_path.write_text(result, encoding='utf-8')
    size_kb = len(result) // 1024
    remote = 'mmbiz.qpic.cn' in result or 'mmecoa.qpic.cn' in result
    print(f'  Fixed: {article_dir.name} ({size_kb}KB, remote={remote})')
    return True


FIX_DIRS = [
    '2022-03-08_戴最可爱的发绳，造最猛的机器人！',
    '2021-05-11_欢迎宁校长莅临指导！',
    '2021-04-23_RoboMaster2021赛事简介',
    '2020-12-31_2020年终总结',
]

for d in FIX_DIRS:
    ad = BASE / d
    if ad.is_dir():
        apply_appmsg_template(ad)
    else:
        print(f'  NOT FOUND: {d}')

print('\nDone fixing appmsg templates.')
