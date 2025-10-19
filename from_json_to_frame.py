import os
import json
import hashlib
from PIL import Image, ImageOps

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

def apply_transform(im: Image.Image, name: str) -> Image.Image:
    """Применяет трансформацию спрайта в соответствии с флагами из JSON."""

    t = (name or "NONE").upper()

    if t in {"NONE", "DEFAULT"}:
        return im

    if t in {"FLIP_H", "MIRROR"}:
        return ImageOps.mirror(im)

    if t == "FLIP_V":
        return ImageOps.flip(im)

    if t == "ROTATE_90":
        return im.transpose(Image.ROTATE_90)

    if t == "ROTATE_180":
        return im.transpose(Image.ROTATE_180)

    if t == "ROTATE_270":
        return im.transpose(Image.ROTATE_270)

    if t == "MIRROR_ROTATE_90":
        return ImageOps.mirror(im).transpose(Image.ROTATE_90)

    if t == "MIRROR_ROTATE_180":
        # В игре этот флаг используется для пистолета: фактически нужен поворот на 90° CCW
        # без дополнительного ресемплинга, иначе появляются "смазанные" пиксели.
        return im.transpose(Image.ROTATE_90)

    if t == "MIRROR_ROTATE_270":
        return ImageOps.mirror(im).transpose(Image.ROTATE_270)

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
        transformed_crop = apply_transform(crop, transform_name)
        final_crop = transformed_crop

        # 3) позиция: absolute_position
        pos_x = int(round(part["absolute_position"]["x"] - fb["x"]))
        pos_y = int(round(part["absolute_position"]["y"] - fb["y"]))

        # 4) накладываем с альфой
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
