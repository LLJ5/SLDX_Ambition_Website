from pathlib import Path
import re, subprocess

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")
repo = Path("D:/SLDX_Ambition_Website")

targets = ["2018-10-24_干事", "2018-10-25_干事", "2021-02-26_今年元夜时"]

for prefix in targets:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    for d in dirs:
        print(f"=== {d.name} ===")
        files = list(d.iterdir())
        for f in sorted(files):
            sz = f.stat().st_size // 1024
            print(f"  {f.name:30s} {sz:>4d} KB")
        
        # Check git for cover.jpg
        rel = f"doc/public/wechat/articles/{d.name}/cover.jpg"
        result = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(repo))
        if result.returncode == 0:
            print(f"  git: has cover.jpg ({len(result.stdout)} bytes)")
            (d / "cover.jpg").write_bytes(result.stdout)
            print(f"  -> Restored!")
        else:
            print(f"  git: no cover.jpg")
        
        # Check git for cover.png
        rel_png = f"doc/public/wechat/articles/{d.name}/cover.png"
        result2 = subprocess.run(["git", "show", f"HEAD:{rel_png}"], capture_output=True, cwd=str(repo))
        if result2.returncode == 0:
            print(f"  git: has cover.png ({len(result2.stdout)} bytes)")
            (d / "cover.png").write_bytes(result2.stdout)
            print(f"  -> Restored cover.png!")
        else:
            print(f"  git: no cover.png")
        
        # Check og:url
        html = (d / "index.html").read_text(encoding="utf-8", errors="replace")
        og_url = re.search(r'content="([^"]+)"\s+property="og:url"', html)
        og_img = re.search(r'content="([^"]+)"\s+property="og:image"', html)
        if og_url: print(f"  og:url: {og_url.group(1)}")
        if og_img: print(f"  og:image: {og_img.group(1)}")
        print()
