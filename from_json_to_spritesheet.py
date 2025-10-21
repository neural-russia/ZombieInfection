from typing import List, Tuple
from PIL import Image

from from_json_to_frame import (
    JSON_PATH,
    SPRITES_DIR,
    load_json,
    index_sprites,
    build_frame,
    trim_to_content,
)

SPRITESHEET_PATH = "capture_0001_spritesheet.png"
CELL_PADDING = 10


def _center_offsets(cell_size: Tuple[int, int], image: Image.Image) -> Tuple[int, int]:
    cell_w, cell_h = cell_size
    offset_x = CELL_PADDING + (cell_w - 2 * CELL_PADDING - image.width) // 2
    offset_y = CELL_PADDING + (cell_h - 2 * CELL_PADDING - image.height) // 2
    return offset_x, offset_y


def main() -> None:
    data = load_json(JSON_PATH)
    frame_keys = data["meta"]["frame_keys"]
    frames = data["frames"]

    hash_to_path = index_sprites(SPRITES_DIR)

    trimmed_frames: List[Tuple[str, Image.Image]] = []

    for key in frame_keys:
        print(f"🧩 Собираем {key} …")
        frame_image = build_frame(key, frames, hash_to_path)
        trimmed, _bbox = trim_to_content(frame_image)
        trimmed_frames.append((key, trimmed))

    if not trimmed_frames:
        print("❌ Нет кадров для экспорта.")
        return

    max_width = max(img.width for _, img in trimmed_frames)
    max_height = max(img.height for _, img in trimmed_frames)

    cell_width = max_width + CELL_PADDING * 2
    cell_height = max_height + CELL_PADDING * 2

    sheet_width = cell_width * len(trimmed_frames)
    sheet_height = cell_height

    spritesheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))

    for idx, (key, img) in enumerate(trimmed_frames):
        print(f"📍 Размещаем {key} в колонке {idx}")
        cell_origin_x = idx * cell_width
        offset_x, offset_y = _center_offsets((cell_width, cell_height), img)
        spritesheet.paste(img, (cell_origin_x + offset_x, offset_y), img)

    spritesheet.save(SPRITESHEET_PATH)
    print(f"✅ Spritesheet сохранён: {SPRITESHEET_PATH}")


if __name__ == "__main__":
    main()
