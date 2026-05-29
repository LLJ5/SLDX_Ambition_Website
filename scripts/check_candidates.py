from pathlib import Path
import cv2
import numpy as np

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")

articles = [
    ("2017-05-31_LED", "LED设计大赛进入决赛阶段"),
    ("2018-10-24_规则", "规则视频发布：3分钟入门机器人比赛指南"),
]

for prefix, title in articles:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    for d in dirs:
        print(f"=== {d.name} ===")
        # Check restored cover
        cover = d / "cover.jpg"
        if cover.exists():
            data = cover.read_bytes()
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                bright = np.mean(img)
                print(f"  Existing cover: {w}x{h} {len(data)//1024}KB bright={bright:.0f}")
            else:
                print(f"  Existing cover: INVALID")

        # Find the first reasonable image to use as cover
        candidates = []
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and f.name.startswith("img_"):
                sz = f.stat().st_size
                if sz > 10000:  # at least 10KB
                    candidates.append((f, sz))
        
        if candidates:
            # Pick the first/largest image
            best_img = candidates[0][0]
            for f, sz in candidates:
                data = f.read_bytes()
                img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    h, w = img.shape[:2]
                    bright = np.mean(img)
                    print(f"  candidate: {f.name} {w}x{h} {sz//1024}KB bright={bright:.0f}")
        print()
