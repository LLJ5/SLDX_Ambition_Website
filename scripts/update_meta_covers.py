"""Update metadata for articles whose covers have been fixed."""
import json
from pathlib import Path

articles = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")
meta_path = articles.parent / "wechat-metadata.json"

data = json.loads(meta_path.read_text(encoding="utf-8"))
updated = 0

fixed_prefixes = [
    "2022-03-08",
    "2021-05-11",
    "2021-04-23",
    "2020-12-31",
    "2020-12-25",
    "2022-03-01",
]

for item in data:
    for prefix in fixed_prefixes:
        if item["dir"].startswith(prefix):
            ad = articles / item["dir"]
            for ext in ("jpg", "png", "webp", "gif"):
                if (ad / f"cover.{ext}").exists():
                    item["hasCover"] = True
                    item["coverExt"] = ext
                    updated += 1
                    sz = (ad / f"cover.{ext}").stat().st_size
                    print(f"{item['dir'][:50]:50s} hasCover=True coverExt={ext} ({sz//1024} KB)")
                    break

meta_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"\nTotal updated: {updated}")
