from pathlib import Path
import re

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")

targets = [
    "2022-03-08",
    "2022-03-01",
    "2021-05-11",
    "2021-04-23",
    "2020-12-31",
    "2020-12-25",
]

for prefix in targets:
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not d.name.startswith(prefix):
            continue
        covers = list(d.glob("cover.*"))
        if covers:
            for c in covers:
                sz = c.stat().st_size
                print(f"{d.name[:50]:50s} -> {c.name:15s} ({sz//1024:>4d} KB)")
        else:
            print(f"{d.name[:50]:50s} -> NO COVER")
        # Also get og:url
        idx = d / "index.html"
        if idx.exists():
            html = idx.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'content="([^"]+)"\s+property="og:url"', html)
            if m:
                print(f"{'':50s}    og:url = {m.group(1)}")
            m2 = re.search(r'content="([^"]+)"\s+property="og:image"', html)
            if m2:
                print(f"{'':50s}    og:image = {m2.group(1)}")
