import re
from pathlib import Path

base = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles')

articles = [
    ('2024-04-20_Ambition战队2024辽宁站混剪来啦！', '1953389486', 'BV1qC41137PB', '1513424507'),
    ('2024-05-22_3D打印耗材赞助开箱——叁生万物', '1854904251', 'BV1Ts421A7zS', '1552968964'),
    ('2024-06-12_Ambition战队24赛季对抗赛MV', '1355629603', 'BV1Yz421b7rM', '1579358944'),
    ('2024-10-24_赞助开箱视频一艾迈斯', '113359504541496', 'BV1Fq1PYPEK6', '26434404865'),
    ('2024-11-26_RoboMaster官方物资开箱视频', '113549187745931', 'BV1N2z3YUERE', '27042187093'),
]

iframe_tpl = '<iframe src="//player.bilibili.com/player.html?isOutside=true&aid={aid}&bvid={bvid}&cid={cid}&p=1&autoplay=0" scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true" width="100%" style="width:100%;aspect-ratio:16/9;display:block"></iframe>'

for dirname, aid, bvid, cid in articles:
    fp = base / dirname / 'index.html'
    html = fp.read_text(encoding='utf-8')
    orig_len = len(html)
    new_iframe = iframe_tpl.format(aid=aid, bvid=bvid, cid=cid)

    # Pattern 1: video channel page (articles 1-4)
    # <div class="js_video_channel_container">...mpvideo_wrp...</div> before sub_info_wrp
    pattern1 = r'(<div class="js_video_channel_container">)(.*?)(</div>\s*<div class="sub_info_wrp")'
    m1 = re.search(pattern1, html, re.DOTALL)
    if m1:
        html = html[:m1.start(2)] + new_iframe + html[m1.end(2):]
        fp.write_text(html, encoding='utf-8')
        print(f'OK (video channel): {dirname}')
        continue

    # Pattern 2: embedded video in article (article 5)
    # <span class="video_iframe rich_pages" ...>...</span>
    pattern2 = r'<span[^>]*video_iframe[^>]*>.*?</span>'
    m2 = re.search(pattern2, html, re.DOTALL)
    if m2:
        html = html[:m2.start()] + new_iframe + html[m2.end():]
        fp.write_text(html, encoding='utf-8')
        print(f'OK (embedded span): {dirname}')
        continue

    print(f'SKIP (no match): {dirname}')

print('Done')
