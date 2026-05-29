import re
h = open(r'D:\SLDX_Ambition_Website\doc\public\wechat\articles\2022-03-01_久等！RoboMaster_机甲大师_2021_赛季纪录预告片正式上线\index.html', encoding='utf-8').read()
m = re.search(r'property="og:url"\s+content="([^"]*)"', h)
print(m.group(1) if m else 'NOT FOUND')
