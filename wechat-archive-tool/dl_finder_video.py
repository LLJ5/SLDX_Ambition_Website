"""Download finder video for 2022-03-01."""
import asyncio, json, time, struct
from pathlib import Path
import sys
sys.path.insert(0, str(Path('.').absolute()))

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={'width':1280,'height':800})
        cf = Path('wechat_cookies.json')
        if cf.exists(): await ctx.add_cookies(json.loads(cf.read_text()))
        page = await ctx.new_page()
        await page.goto('https://mp.weixin.qq.com/s/se4sF9Z5hBUGDwrrmzjPbg',
                         wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        url = await page.evaluate("document.querySelector('mp-common-videosnap').getAttribute('data-url')")
        print('URL:', url[:150])

        start = time.time()
        result = await page.evaluate('''async (u) => {
            const r = await fetch(u); if (!r.ok) return {status:r.status};
            const buf = await r.arrayBuffer();
            return {status:r.status,size:buf.byteLength,data:Array.from(new Uint8Array(buf))};
        }''', url)
        elapsed = time.time() - start
        print(f'status={result.get("status")} size={result.get("size")} time={elapsed:.1f}s')

        if result.get('data') and result['size'] > 50000:
            data = bytes(result['data'])
            out = Path('../doc/public/wechat/articles/2022-03-01_久等！RoboMaster_机甲大师_2021_赛季纪录预告片正式上线/video_1.mp4')
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            print(f'Saved: {len(data)//1024}KB')
            res = parse_res(data)
            print(f'Resolution: {res}')
        else:
            print(f'Fetch too small ({result.get("size")}B), trying page navigation...')
            # Navigate to the stodownload URL and capture video response
            captured = {}
            async def hdl(response):
                u = response.url
                ct = response.headers.get('content-type', '')
                if 'video' in ct and u not in captured:
                    try:
                        body = await response.body()
                        if body and len(body) > 50000:
                            captured[u] = body
                            print(f'  Captured: {len(body)}B')
                    except: pass
            page.on('response', hdl)
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)
            except: pass
            if captured:
                u, d = next(iter(captured.items()))
                out = Path('../doc/public/wechat/articles/2022-03-01_久等！RoboMaster_机甲大师_2021_赛季纪录预告片正式上线/video_1.mp4')
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(d)
                print(f'Saved via nav: {len(d)//1024}KB')
                res = parse_res(d)
                print(f'Resolution: {res}')
            else:
                print('Navigation also failed')
        await browser.close()

def parse_res(data):
    offset = 0; end = len(data)
    while offset + 8 <= end:
        size = struct.unpack('>I', data[offset:offset+4])[0]
        bt = data[offset+4:offset+8].decode('ascii', errors='ignore')
        if size < 8: break
        hs = 8
        if size == 1: size = struct.unpack('>Q', data[offset+8:offset+16])[0]; hs = 16
        be = min(offset + size, end)
        if bt == 'tkhd':
            inner = data[offset+hs:be]; v = inner[0]; p = 4
            p += 8 if v == 1 else 4; p += 8 if v == 1 else 4; p += 4; p += 4
            p += 8 if v == 1 else 4; p += 8; p += 2+2+2+2; p += 36
            return (struct.unpack('>I', inner[p:p+4])[0]>>16, struct.unpack('>I', inner[p+4:p+8])[0]>>16)
        elif bt in ('moov','trak','mdia','minf','stbl'):
            r = parse_res(data[offset+hs:be])
            if r: return r
        offset = be
    return None

asyncio.run(main())
