"""Fix: remove width/height HTML attrs, keep only CSS aspect-ratio and wrapper section."""
import struct
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

def parse_boxes(data, offset, end):
    while offset + 8 <= end:
        size = struct.unpack('>I', data[offset:offset+4])[0]
        box_type = data[offset+4:offset+8].decode('ascii', errors='ignore')
        if size < 8: break
        header_size = 8
        if size == 1:
            size = struct.unpack('>Q', data[offset+8:offset+16])[0]
            header_size = 16
        box_end = min(offset + size, end)
        if box_type == 'tkhd':
            inner = data[offset+header_size:box_end]
            version = inner[0]
            pos = 4
            pos += 8 if version == 1 else 4
            pos += 8 if version == 1 else 4
            pos += 4; pos += 4
            pos += 8 if version == 1 else 4
            pos += 8; pos += 2+2+2+2; pos += 36
            w_raw = struct.unpack('>I', inner[pos:pos+4])[0]
            h_raw = struct.unpack('>I', inner[pos+4:pos+8])[0]
            return (w_raw >> 16, h_raw >> 16)
        elif box_type in ('moov','trak','mdia','minf','stbl'):
            r = parse_boxes(data, offset+header_size, box_end)
            if r: return r
        offset = box_end
    return None

for d in DIRS:
    ad = BASE / d
    video_file = ad / 'video_1.mp4'
    if not video_file.exists(): continue

    data = video_file.read_bytes()
    res = parse_boxes(data, 0, len(data))
    if not res:
        print(f'{d[:30]}: resolution not found'); continue

    w, h = res
    print(f'{d[:30]}: {w}x{h}')

    html_path = ad / 'index.html'
    html = html_path.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')

    for video in soup.find_all('video'):
        src = video.get('src', '')
        if 'video_1.mp4' not in src: continue

        # Clean all attributes
        for attr in list(video.attrs):
            del video[attr]
        video['src'] = src
        video['controls'] = ''
        video['preload'] = 'auto'
        video['style'] = f'width:100%;aspect-ratio:{w}/{h};display:block;background:#000'

    result = str(soup).replace('&amp;', '&')
    html_path.write_text(result, encoding='utf-8')

print('\nDone')
