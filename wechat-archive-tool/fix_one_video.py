from pathlib import Path
from bs4 import BeautifulSoup

ad = Path(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles\2023-03-31_23_赛季_平衡步兵专访')
h = (ad/'index.html').read_text('utf-8', errors='ignore')
soup = BeautifulSoup(h, 'lxml')

# Get sorted video files
video_files = sorted([f.name for f in ad.glob('video_*.mp4') if not f.name.startswith('video_wxv')])
# Also include wxv-named files if needed
wxv_files = sorted([f.name for f in ad.glob('video_wxv_*.mp4')])
all_videos = video_files + wxv_files

viframes = soup.find_all('span', class_='video_iframe')
print(f'video_iframe elements: {len(viframes)}')
print(f'local video files: {all_videos}')

# Replace video_iframe with <video> tags
for i, vf in enumerate(viframes):
    if i < len(all_videos):
        tag = soup.new_tag('video')
        tag['src'] = all_videos[i]
        tag['controls'] = ''
        tag['style'] = 'max-width:100%;width:100%'
        vf.replace_with(tag)
        print(f'  Replaced with <video src="{all_videos[i]}">')

result = str(soup)
result = result.replace('&amp;', '&')
(ad/'index.html').write_text(result, 'utf-8')
print('HTML updated.')
