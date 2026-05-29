from pathlib import Path
import re
import subprocess

base = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")
repo = Path("D:/SLDX_Ambition_Website")

for prefix in ["2017-05-31_LED", "2018-10-24_规则"]:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    for d in dirs:
        print(f"Dir: {d.name}")
        # Check git for cover.jpg
        rel = f"doc/public/wechat/articles/{d.name}/cover.jpg"
        result = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(repo))
        if result.returncode == 0:
            print(f"  git HEAD: has cover.jpg ({len(result.stdout)} bytes)")
            (d / "cover.jpg").write_bytes(result.stdout)
            print(f"  -> Restored to disk!")
        else:
            print(f"  git HEAD: no cover.jpg")
            result2 = subprocess.run(["git", "log", "--all", "--oneline", "--diff-filter=A", "--", rel],
                capture_output=True, text=True, cwd=str(repo))
            print(f"  git log: {result2.stdout.strip() or 'none'}")
        print()
