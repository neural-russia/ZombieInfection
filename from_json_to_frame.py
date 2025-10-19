import os
import json
import hashlib
from PIL import Image

# --------------- НАСТРОЙКИ ---------------
JSON_PATH = "capture_0001.json"
SPRITES_DIR = "sprites"
OUTPUT_DIR = "frames"
GIF_PATH = "capture_0001.gif"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------- ХЭШ ARGB (совместим с твоим Java) ---------------
def sha256_java_argb(img: Image.Image) -> str:
    rgba = img.convert("RGBA")
    try:
        raw = rgba.tobytes("raw", "ARGB")
    except Exception:
        buf = bytearray()
        for r, g, b, a in rgba.getdata():
            buf.extend((a, r, g, b))
        raw = bytes(buf)
    return hashlib.sha256(raw).hexdigest()

# --------------- ТРАНСФОРМ ---------------

from PIL import Image


def apply_transform(im: Image.Image, name: str) -> Image.Image:
    """
    Универсальная функция трансформаций с финальным исправлением
    для случая 'MIRROR_ROTATE_180'.
    """
    t = (name or "NONE").upper()

    # --- Простые трансформации, не меняющие размеры ---
    if t == "NONE":
        return im
    if t in ("FLIP_H", "MIRROR"):
        return im.transpose(Image.FLIP_LEFT_RIGHT)
    if t == "FLIP_V":
        return im.transpose(Image.FLIP_TOP_BOTTOM)
    if t == "ROTATE_180":
        return im.transpose(Image.ROTATE_180)

    # --- НАШ СЛУЧАЙ: Неверно названная трансформация ---
    # Судя по вашему тесту, эта операция на самом деле является поворотом на 90 градусов.
    # Применяем безопасный поворот через паддинг, чтобы избежать обрезки и искажения.
    if t == "MIRROR_ROTATE_180":
        w, h = im.size

        # Создаем временный холст, чтобы избежать обрезки
        padding = 2
        side = max(w, h) + padding * 2
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        offset_x = (side - w) // 2
        offset_y = (side - h) // 2
        square.paste(im, (offset_x, offset_y), im)

        # Применяем поворот на 90 градусов (CCW), который дал правильную ориентацию
        rotated_square = square.transpose(Image.ROTATE_90)

        # Вырезаем центральную часть, но уже с инвертированными размерами (h x w)
        crop_x = (side - h) // 2
        crop_y = (side - w) // 2

        # Возвращаем повернутое изображение без искажений
        return rotated_square.crop((crop_x, crop_y, crop_x + h, crop_y + w))

    # --- Другие трансформации, которые могут менять размеры ---
    # (Оставим общую логику для них на всякий случай)
    if t in ("ROTATE_90", "ROTATE_270", "MIRROR_ROTATE_90", "MIRROR_ROTATE_270"):
        # Здесь можно будет использовать ту же логику с паддингом,
        # если эти трансформации тоже будут вызывать проблемы.
        # Пока что можно оставить как есть или использовать код из предыдущего ответа.
        # Для чистоты, применим тот же безопасный метод:

        # Определяем, какую операцию Pillow нужно вызвать
        op = None
        if t == "ROTATE_90":
            op = Image.ROTATE_270  # В Pillow они инвертированы
        elif t == "ROTATE_270":
            op = Image.ROTATE_90

        if op:
            # Создаем временный холст
            w, h = im.size
            padding = 2
            side = max(w, h) + padding * 2
            square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            offset_x = (side - w) // 2
            offset_y = (side - h) // 2
            square.paste(im, (offset_x, offset_y), im)

            rotated_square = square.transpose(op)

            crop_x = (side - h) // 2
            crop_y = (side - w) // 2
            return rotated_square.crop((crop_x, crop_y, crop_x + h, crop_y + w))

    return im






# --------------- ЗАГРУЗКА JSON ---------------
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

frame_keys = data["meta"]["frame_keys"]
frames = data["frames"]

# --------------- ИНДЕКС ПО ХЭШУ ---------------
print("📦 Индексируем изображения...")
hash_to_path = {}
for fname in os.listdir(SPRITES_DIR):
    if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        continue
    path = os.path.join(SPRITES_DIR, fname)
    try:
        with Image.open(path) as im:
            digest = sha256_java_argb(im)
            hash_to_path[digest] = path
    except Exception as e:
        print(f"⚠️ Не удалось прочитать {fname}: {e}")
print(f"✅ Индексировано {len(hash_to_path)} изображений.")

# --------------- СБОРКА ОДНОГО КАДРА ---------------
def build_frame(frame_key: str) -> Image.Image:
    frame = frames[frame_key]
    fb = frame["bounds"]
    parts = frame["parts"]

    # Прозрачный холст
    canvas = Image.new("RGBA", (fb["width"], fb["height"]), (0, 0, 0, 0))

    for part in sorted(parts, key=lambda p: p["order"]):
        sh = part.get("sprite_hash", {})
        sprite_hash = (sh.get("value") or "").lower()
        if not sprite_hash:
            continue

        sprite_path = hash_to_path.get(sprite_hash)
        if not sprite_path:
            print(f"⏭️ {frame_key}: нет файла для hash={sprite_hash[:8]}… — пропуск")
            continue

        sprite = Image.open(sprite_path).convert("RGBA")

        # 1) crop из source в координатах исходного спрайта
        src = part["source"]
        crop = sprite.crop((src["x"], src["y"], src["x"] + src["width"], src["y"] + src["height"]))

        # 2) применяем трансформацию
        transform_name = (part.get("transform", {}).get("name") or "NONE")
        transformed_crop = apply_transform(crop, transform_name, 0, 0)  # Размеры не важны

        # 3) подгоняем под итоговый размер (после трансформации)
        dst_w, dst_h = part["size"]["width"], part["size"]["height"]
        if transformed_crop.size != (dst_w, dst_h):
            final_crop = transformed_crop.resize((dst_w, dst_h), Image.NEAREST)
        else:
            final_crop = transformed_crop

        # 4) позиция: absolute_position
        pos_x = int(round(part["absolute_position"]["x"] - fb["x"]))
        pos_y = int(round(part["absolute_position"]["y"] - fb["y"]))

        # 5) накладываем с альфой
        canvas.paste(final_crop, (pos_x, pos_y), final_crop)

    return canvas

# --------------- СБОРКА ВСЕХ КАДРОВ ---------------
assembled = []
durations = []
for key in frame_keys:
    print(f"🧩 Собираем {key} …")
    img = build_frame(key)
    img.save(os.path.join(OUTPUT_DIR, f"{key}.png"))
    assembled.append(img)
    durations.append(frames[key].get("duration_ms", 40))  # fallback 40ms

print(f"✅ Собрано кадров: {len(assembled)}")

# --------------- ЭКСПОРТ GIF ---------------
if assembled:
    print("🎞️ Экспорт GIF …")
    first, *rest = assembled
    # transparency/disposal для лучшей прозрачности и перерисовки
    first.save(
        GIF_PATH,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=0,
        disposal=2,      # restore to background
        transparency=0,  # индекс прозрачности; Pillow сам подставит, но оставим параметр
    )
    print(f"🎬 GIF сохранён: {GIF_PATH}")
else:
    print("❌ Нет кадров для экспорта.")
