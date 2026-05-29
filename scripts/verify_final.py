import cv2, numpy as np
from pathlib import Path
base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")
for prefix in ["2018-10-24_干事", "2018-10-25_干事", "2021-02-26"]:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    for d in dirs:
        c = d / "cover.jpg"
        if c.exists():
            data = c.read_bytes()
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            h, w = img.shape[:2]
            print(f"{d.name[:55]:55s} -> {w}x{h} {len(data)//1024}KB bright={np.mean(img):.0f}")
