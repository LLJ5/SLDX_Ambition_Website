from pathlib import Path
import re, subprocess, cv2, numpy as np

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")
repo = Path("D:/SLDX_Ambition_Website")

# Check 2021-02-26 separately
dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("2021-02-26")]
for d in dirs:
    print(f"=== {d.name} ===")
    files = list(d.iterdir())
    for f in sorted(files):
        sz = f.stat().st_size // 1024
        print(f"  {f.name:30s} {sz:>4d} KB")
    
    rel = f"doc/public/wechat/articles/{d.name}/cover.jpg"
    result = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(repo))
    if result.returncode == 0:
        print(f"  git: has cover.jpg ({len(result.stdout)} bytes)")
        (d / "cover.jpg").write_bytes(result.stdout)
        print(f"  -> Restored!")
    else:
        print(f"  git: no cover.jpg")
        # Check for video
        videos = list(d.glob("video_1.*"))
        if videos:
            print(f"  has video: {videos[0].name}")

# Now check quality of ALL restored covers
print("\n=== Quality check ===")
for prefix in ["2018-10-24_干事", "2018-10-25_干事", "2021-02-26"]:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    for d in dirs:
        cover = d / "cover.jpg"
        if cover.exists():
            data = cover.read_bytes()
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                bright = np.mean(img)
                print(f"{d.name[:55]:55s} -> {w}x{h} {len(data)//1024}KB bright={bright:.0f}")
            else:
                print(f"{d.name[:55]:55s} -> INVALID")
        else:
            # Check if it has cover.png
            cover_png = d / "cover.png"
            if cover_png.exists():
                print(f"{d.name[:55]:55s} -> has cover.png only")
            else:
                print(f"{d.name[:55]:55s} -> STILL NO COVER")
