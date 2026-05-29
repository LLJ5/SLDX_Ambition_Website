"""Re-generate covers for specific video articles with better frame selection."""
import cv2
import numpy as np
from pathlib import Path

ARTICLES = Path("D:/SLDX_Ambition_Website/doc/public/wechat/articles")

# Articles the user reported issues with
targets = [
    "2022-03-08",  # 戴最可爱的发绳，造最猛的机器人！
    "2021-05-11",  # 欢迎宁校长莅临指导！
    "2021-04-23",  # RoboMaster2021赛事简介
    "2020-12-31",  # 2020年终总结
    "2020-12-25",  # 快乐的圣诞节
]


def get_best_frame(cap, total_frames, fps):
    """Try frames at 10%, 25%, 50% and pick the brightest one."""
    candidates = [
        int(total_frames * 0.1),
        int(total_frames * 0.25),
        int(total_frames * 0.5),
        int(fps * 3),  # 3 seconds in
    ]
    candidates = [max(1, min(f, total_frames - 1)) for f in candidates]
    candidates = list(set(candidates))  # deduplicate

    best_frame = None
    best_brightness = -1

    for pos in candidates:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if not ret:
            continue
        brightness = np.mean(frame)
        if brightness > best_brightness:
            best_brightness = brightness
            best_frame = frame

    if best_frame is None:
        # Fallback: try first frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, 1)
        ret, best_frame = cap.read()

    return best_frame


def main():
    for prefix in targets:
        dirs = [d for d in ARTICLES.iterdir() if d.is_dir() and d.name.startswith(prefix)]
        if not dirs:
            print(f"No directory found for {prefix}")
            continue

        article_dir = dirs[0]
        video = None
        for f in article_dir.glob("video_1.*"):
            video = f
            break

        if not video:
            print(f"{article_dir.name[:45]} -> NO VIDEO, skipping")
            continue

        print(f"Processing: {article_dir.name[:55]}")

        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            print(f"  Cannot open video")
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"  Video: {total_frames} frames, {fps:.1f} fps")

        frame = get_best_frame(cap, total_frames, fps)
        cap.release()

        if frame is None:
            print(f"  FAILED: could not read any frame")
            continue

        # Remove old cover
        for c in article_dir.glob("cover.*"):
            c.unlink()
            print(f"  Removed old {c.name}")

        # Save new cover
        cover_path = article_dir / "cover.jpg"
        success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if success:
            cover_path.write_bytes(buf.tobytes())
            sz = cover_path.stat().st_size
            brightness = np.mean(frame)
            dark_pct = np.sum(frame < 30) / frame.size * 100
            print(f"  OK: cover.jpg ({sz//1024} KB, bright={brightness:.0f}, dark={dark_pct:.0f}%)")
        else:
            print(f"  FAILED: could not encode JPEG")


if __name__ == "__main__":
    main()
