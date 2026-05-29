from pathlib import Path
import re, cv2, numpy as np

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")

# Search by title keywords
keywords = ["今年元夜时", "干事邀请函"]

found = []
for d in sorted(base.iterdir()):
    if not d.is_dir() or d.name == "_shared":
        continue
    html = d / "index.html"
    if not html.exists():
        continue
    content = html.read_text(encoding="utf-8", errors="replace")
    title_m = re.search(r"<title>(.*?)</title>", content)
    if not title_m:
        continue
    title = title_m.group(1)
    for kw in keywords:
        if kw in title:
            covers = list(d.glob("cover.*"))
            sz = ""
            if covers:
                c = covers[0]
                data = c.read_bytes()
                img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    h, w = img.shape[:2]
                    bright = np.mean(img)
                    sz = f"{c.name} {w}x{h} {len(data)//1024}KB bright={bright:.0f}"
                else:
                    sz = f"{c.name} INVALID"
            else:
                sz = "NO COVER"
            print(f"{d.name[:55]:55s} | {title[:45]:45s} | {sz}")
            found.append(d)
            break

print(f"\nTotal found: {len(found)}")
