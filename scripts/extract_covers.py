"""Extract first frame from video as cover.jpg for articles missing covers."""
import json
import re
from pathlib import Path

import cv2

ARTICLES = Path(__file__).resolve().parent.parent / "doc" / "public" / "wechat" / "articles"
METADATA = ARTICLES.parent / "wechat-metadata.json"


def has_cover(article_dir: Path) -> bool:
    for ext in ("jpg", "png", "webp", "gif"):
        if (article_dir / f"cover.{ext}").exists():
            return True
    return False


def get_video_path(article_dir: Path):
    for f in article_dir.glob("video_1.*"):
        return f
    return None


def extract_cover(video_path: Path, output_path: Path) -> bool:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  ERROR: Cannot open video: {video_path}")
        return False

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Skip past intro - take frame at ~2 seconds or 10% into video, whichever is later
    target_frame = int(max(fps * 2, total_frames * 0.1))
    target_frame = min(target_frame, total_frames - 1)

    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print(f"  ERROR: Cannot read frame {target_frame}")
        return False

    # Use imencode + write bytes to handle Unicode paths
    success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not success:
        print(f"  ERROR: Cannot encode frame as JPEG")
        return False
    output_path.write_bytes(buf.tobytes())
    return True


def is_bad_cover(article_dir: Path) -> bool:
    """Check if cover is too dark or too small."""
    import numpy as np
    cover = None
    for ext in ("jpg", "png", "webp"):
        c = article_dir / f"cover.{ext}"
        if c.exists():
            cover = c
            break
    if cover is None:
        return True
    if cover.stat().st_size < 5000:
        return True  # too small, likely black/broken
    # Decode and check brightness
    data = cover.read_bytes()
    np_data = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
    if img is None:
        return True
    brightness = np.mean(img)
    return brightness < 20  # too dark


def update_metadata_for_dirs(dirs: list):
    """Update metadata for a list of directory names."""
    if not METADATA.exists():
        return
    import json
    raw = METADATA.read_text(encoding="utf-8")
    data = json.loads(raw)
    updated = 0
    for item in data:
        if item["dir"] in dirs:
            # Detect cover extension
            article_dir = ARTICLES / item["dir"]
            for ext in ("jpg", "png", "webp", "gif"):
                if (article_dir / f"cover.{ext}").exists():
                    item["hasCover"] = True
                    item["coverExt"] = ext
                    updated += 1
                    break
    if updated:
        METADATA.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Metadata updated: {updated} entries")


def main():
    force_redos = []  # articles to regenerate even if cover exists
    missing = []
    for entry in sorted(ARTICLES.iterdir()):
        if entry.name == "_shared" or not entry.is_dir():
            continue
        if not has_cover(entry):
            missing.append(entry)
        elif is_bad_cover(entry):
            force_redos.append(entry)

    print(f"Articles missing covers: {len(missing)}")
    print(f"Articles with bad covers (will redo): {len(force_redos)}")
    # Process missing ones
    for entry in force_redos:
        cover = None
        for ext in ("jpg", "png", "webp"):
            c = entry / f"cover.{ext}"
            if c.exists():
                cover = c
                break
        if cover:
            cover.unlink()  # remove bad cover
        missing.append(entry)

    fixed = []
    failed = []
    for article_dir in missing:
        print(f"\nProcessing: {article_dir.name}")
        video = get_video_path(article_dir)
        if video is None:
            print(f"  SKIP: no video found")
            continue

        cover_path = article_dir / "cover.jpg"
        if extract_cover(video, cover_path) and cover_path.exists():
            size_kb = cover_path.stat().st_size / 1024
            print(f"  OK: cover.jpg created ({size_kb:.0f} KB)")
            fixed.append(article_dir.name)
        else:
            print(f"  FAILED")
            failed.append(article_dir.name)

    print(f"\n=== Summary ===")
    print(f"Fixed: {len(fixed)}")
    for d in fixed:
        print(f"  - {d}")
    if failed:
        print(f"Failed: {len(failed)}")
        for d in failed:
            print(f"  - {d}")

    # Update metadata
    if fixed:
        update_metadata(fixed)


def update_metadata(fixed_dirs: list):
    if not METADATA.exists():
        print("Metadata file not found, skipping update")
        return

    raw = METADATA.read_text(encoding="utf-8")
    metadata = json.loads(raw)

    updated = 0
    for item in metadata:
        if item["dir"] in fixed_dirs:
            item["hasCover"] = True
            item["coverExt"] = "jpg"
            updated += 1

    if updated:
        METADATA.write_text(
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"\nMetadata updated: {updated} entries")


if __name__ == "__main__":
    main()
