import cv2
import numpy as np
import json
from pathlib import Path

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")

# 2017-05-31_LED设计大赛进入决赛阶段
led_dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("2017-05-31_LED")]
for d in led_dirs:
    # img_7.jpg is brightest good-sized candidate
    src = d / "img_7.jpg"
    dst = d / "cover.jpg"
    data = src.read_bytes()
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    # Resize to a reasonable cover size (640 width)
    new_w = 640
    new_h = int(h * new_w / w)
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    success, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if success:
        if dst.exists(): dst.unlink()
        dst.write_bytes(buf.tobytes())
        print(f"LED article: cover.jpg created from img_7.jpg ({dst.stat().st_size//1024} KB, bright={np.mean(img):.0f})")
    else:
        print(f"LED article: FAILED to create cover")

# 2018-10-24_规则视频发布：《3分钟入门机器人比赛指南》
rule_dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("2018-10-24_规则")]
for d in rule_dirs:
    # img_8.webp is largest, good brightness
    src = d / "img_8.webp"
    dst = d / "cover.jpg"
    data = src.read_bytes()
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    # Resize to 640 width for consistency
    new_w = 640
    new_h = int(h * new_w / w)
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    success, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if success:
        if dst.exists(): dst.unlink()
        dst.write_bytes(buf.tobytes())
        print(f"Rule article: cover.jpg created from img_8.webp ({dst.stat().st_size//1024} KB, bright={np.mean(img):.0f})")
    else:
        print(f"Rule article: FAILED to create cover")

# Update metadata
meta_path = Path("D:/SLDX_Ambition_Website/doc/public/wechat/wechat-metadata.json")
data = json.loads(meta_path.read_text(encoding="utf-8"))
updated = 0
for item in data:
    for prefix in ["2017-05-31_LED", "2018-10-24_"]:
        if item["dir"].startswith(prefix):
            ad = base / item["dir"]
            for ext in ("jpg", "png", "webp", "gif"):
                if (ad / f"cover.{ext}").exists():
                    sz = (ad / f"cover.{ext}").stat().st_size
                    item["hasCover"] = True
                    item["coverExt"] = ext
                    updated += 1
                    print(f"Metadata: {item['dir'][:55]:55s} -> {ext} ({sz//1024} KB)")
                    break
meta_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"Metadata updated: {updated} entries")
