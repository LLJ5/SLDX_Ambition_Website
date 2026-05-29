from pathlib import Path
import cv2, numpy as np, json

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")

articles = [
    ("2018-10-24_", "干事邀请函 2018-10-24"),
    ("2018-10-25_", "干事邀请函 2018-10-25"),
    ("2021-02-26_", "今年元夜时，月与灯依旧"),
]

for prefix, label in articles:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    for d in dirs:
        print(f"=== {d.name} ===")
        # Find all images, pick the best one as cover
        candidates = []
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and f.name.startswith("img_"):
                sz = f.stat().st_size
                if sz < 5000:
                    continue  # skip tiny images
                data = f.read_bytes()
                img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    h, w = img.shape[:2]
                    bright = np.mean(img)
                    # Prefer larger, brighter images
                    score = bright * w * h
                    candidates.append((score, f.name, img, w, h, bright, sz))

        candidates.sort(key=lambda x: -x[0])

        if candidates:
            score, name, img, w, h, bright, sz = candidates[0]
            print(f"  Best candidate: {name} {w}x{h} {sz//1024}KB bright={bright:.0f}")

            # Resize to reasonable cover size
            new_w = 640
            new_h = int(h * new_w / w)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            cover = d / "cover.jpg"
            success, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if success:
                if cover.exists(): cover.unlink()
                cover.write_bytes(buf.tobytes())
                print(f"  -> cover.jpg created ({cover.stat().st_size//1024} KB)")
        else:
            print(f"  No suitable image found")

# Update metadata
print("\n=== Updating metadata ===")
meta_path = base.parent / "wechat-metadata.json"
data = json.loads(meta_path.read_text(encoding="utf-8"))
updated = 0
for item in data:
    for prefix in ["2018-10-24_干事", "2018-10-25_干事", "2021-02-26"]:
        if item["dir"].startswith(prefix):
            ad = base / item["dir"]
            for ext in ("jpg", "png", "webp", "gif"):
                if (ad / f"cover.{ext}").exists():
                    sz = (ad / f"cover.{ext}").stat().st_size
                    item["hasCover"] = True
                    item["coverExt"] = ext
                    updated += 1
                    print(f"  {item['dir'][:55]:55s} -> {ext} ({sz//1024} KB)")
                    break

meta_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"Total metadata updated: {updated}")
