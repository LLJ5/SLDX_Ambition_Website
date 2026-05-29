
import re
from pathlib import Path

base = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')
ref_dir = next(base.glob('2024-11-26_*小雪*'))
ref_html = (ref_dir / 'index.html').read_text(encoding='utf-8')
ref_head = ref_html[:ref_html.find('</head>')]

def get_meta(html, pattern):
    m = re.search(pattern, html)
    return m.group(1) if m else ''

def fix_article(kw):
    for d in base.glob(kw):
        html = (d / 'index.html').read_text(encoding='utf-8')
        body = html[html.find('<body'):]
        body = body.replace(
            'class="share_content_page_bd" id="js_base_container"',
            'class="share_content_page_bd" id="js_base_container" style="width:500px !important"'
        )
        head = ref_head
        for key, pattern in [
            ('OG_TITLE', r'property="og:title"\s+content="([^"]*)"'),
            ('OG_URL', r'property="og:url"\s+content="([^"]*)"'),
            ('OG_IMAGE', r'property="og:image"\s+content="([^"]*)"'),
            ('DESC', r'name="description"\s+content="([^"]*)"'),
            ('OG_DESC', r'property="og:description"\s+content="([^"]*)"'),
            ('AUTHOR', r'name="author"\s+content="([^"]*)"'),
            ('TWITTER_TITLE', r'name="twitter:title"\s+content="([^"]*)"'),
            ('TWITTER_IMAGE', r'name="twitter:image"\s+content="([^"]*)"'),
            ('TWITTER_DESC', r'name="twitter:description"\s+content="([^"]*)"'),
        ]:
            tv = get_meta(html, pattern)
            wv = get_meta(head, pattern)
            if wv and tv:
                head = head.replace(wv, tv)
        
        tt = re.search(r'<title>(.*?)</title>', html)
        wt = re.search(r'<title>(.*?)</title>', head)
        if tt and wt and tt.group(1) != wt.group(1):
            head = head.replace(wt.group(1), tt.group(1))
        
        new_html = '<!DOCTYPE html>\n' + head + '</head>\n' + body
        (d / 'index.html').write_text(new_html, encoding='utf-8')
        print(f'{d.name}: ok')

fix_article('2025-03-25_*倒计时2*')
fix_article('2025-03-26_*倒计时1*')
print('Done')
