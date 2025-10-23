from typing import List

from PIL import Image

from from_json_to_frame import FrameData, JSON_PATH, SPRITES_DIR, assemble_frames

SPRITESHEET_PATH = "capture_0001_spritesheet.png"
CELL_PADDING = 10


def build_spritesheet(
    frames: List[FrameData],
    path: str,
    *,
    cell_padding: int = CELL_PADDING,
) -> None:
    if not frames:
        print("❌ Нет кадров для экспорта.")
        return

    max_width = max(frame.trimmed.width for frame in frames)
    max_height = max(frame.trimmed.height for frame in frames)

    cell_width = max_width + cell_padding * 2
    cell_height = max_height + cell_padding * 2

    sheet_width = cell_width * len(frames)
    sheet_height = cell_height

    spritesheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))

    for idx, frame in enumerate(frames):
        print(f"📍 Размещаем {frame.key} в колонке {idx}")
        cell_origin_x = idx * cell_width
        offset_x = cell_padding + (cell_width - 2 * cell_padding - frame.trimmed.width) // 2
        offset_y = cell_padding + (cell_height - 2 * cell_padding - frame.trimmed.height) // 2
        spritesheet.paste(frame.trimmed, (cell_origin_x + offset_x, offset_y), frame.trimmed)

    spritesheet.save(path)
    print(f"✅ Spritesheet сохранён: {path}")


if __name__ == "__main__":
    frames = assemble_frames(JSON_PATH, SPRITES_DIR)
    build_spritesheet(frames, SPRITESHEET_PATH)
