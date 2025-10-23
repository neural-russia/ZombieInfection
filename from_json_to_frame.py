import os
import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List, Callable, Iterable

from PIL import Image, ImageOps

# --------------- НАСТРОЙКИ ---------------
JSON_PATH = "capture_0001.json"
SPRITES_DIR = "sprites"
OUTPUT_DIR = "frames"
GIF_PATH = "capture_0001.gif"


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
_TransformKey = Tuple[str, str]

# Спрайт пистолета в JSON помечен как MIRROR_ROTATE_180, но визуально
# требуется поворот на 90° CCW. Чтобы не ломать остальные детали, можно
# переопределить трансформацию по идентификатору (или хэшу) спрайта.
DEFAULT_TRANSFORM_OVERRIDES: Dict[_TransformKey, Dict[str, str]] = {
    ("sprite_id", "344"): {"MIRROR_ROTATE_180": "ROTATE_90"},
    ("sprite_id", "345"): {"MIRROR_ROTATE_180": "ROTATE_90"},
    ("sprite_id", "393"): {"MIRROR_ROTATE_180": "ROTATE_90"},
}

# Для совместимости с прежними импортами
TRANSFORM_OVERRIDES = DEFAULT_TRANSFORM_OVERRIDES


def merge_transform_overrides(
    *overrides_dicts: Iterable[Tuple[_TransformKey, Dict[str, str]]]
) -> Dict[_TransformKey, Dict[str, str]]:
    """Объединяет несколько словарей оверрайдов в один."""

    merged: Dict[_TransformKey, Dict[str, str]] = {}
    for overrides in overrides_dicts:
        if overrides is None:
            continue
        if isinstance(overrides, dict):
            items = overrides.items()
        else:
            items = overrides
        for key, mapping in items:
            if not isinstance(mapping, dict):
                mapping = dict(mapping)
            bucket = merged.setdefault(key, {})
            bucket.update(mapping)
    return merged


def load_transform_overrides(path: str) -> Dict[_TransformKey, Dict[str, str]]:
    """Загружает оверрайды трансформаций из JSON-файла."""

    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if not isinstance(payload, list):
        raise ValueError("Файл оверрайдов должен содержать список объектов")

    result: Dict[_TransformKey, Dict[str, str]] = {}
    for idx, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValueError(f"Элемент №{idx + 1} в файле оверрайдов должен быть объектом")

        target_key: Optional[_TransformKey] = None
        if "sprite_id" in entry:
            target_key = ("sprite_id", str(entry["sprite_id"]))
        elif "sprite_hash" in entry:
            target_key = ("sprite_hash", str(entry["sprite_hash"]).lower())

        if not target_key:
            raise ValueError(
                "Каждый оверрайд должен содержать ключ 'sprite_id' или 'sprite_hash'"
            )

        mapping = {
            k.upper(): str(v).upper()
            for k, v in entry.items()
            if k not in {"sprite_id", "sprite_hash"}
        }
        if not mapping:
            raise ValueError(
                f"В оверрайде для {target_key} не найдено ни одной замены трансформации"
            )

        result.setdefault(target_key, {}).update(mapping)

    return result


def _resolve_overrides(
    extra_overrides: Optional[Dict[_TransformKey, Dict[str, str]]]
) -> Dict[_TransformKey, Dict[str, str]]:
    if extra_overrides:
        return merge_transform_overrides(DEFAULT_TRANSFORM_OVERRIDES, extra_overrides)
    return dict(DEFAULT_TRANSFORM_OVERRIDES)


def _normalize_transform(
    name: str,
    sprite_id: Optional[int],
    sprite_hash: Optional[str],
    overrides: Optional[Dict[_TransformKey, Dict[str, str]]] = None,
) -> str:
    """Возвращает финальное название трансформации с учётом оверрайдов."""

    norm = (name or "NONE").upper()

    if overrides is None:
        overrides = DEFAULT_TRANSFORM_OVERRIDES

    if sprite_id is not None:
        override = overrides.get(("sprite_id", str(sprite_id)))
        if override and norm in override:
            return override[norm]

    if sprite_hash:
        override = overrides.get(("sprite_hash", sprite_hash.lower()))
        if override and norm in override:
            return override[norm]

    return norm


def apply_transform(
    im: Image.Image,
    name: str,
    *,
    sprite_id: Optional[int] = None,
    sprite_hash: Optional[str] = None,
    overrides: Optional[Dict[_TransformKey, Dict[str, str]]] = None,
) -> Image.Image:
    """Применяет трансформацию спрайта в соответствии с флагами из JSON."""

    t = _normalize_transform(name, sprite_id, sprite_hash, overrides)

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
        # По данным формата это горизонтальное отражение + поворот на 180°,
        # что эквивалентно вертикальному флипу без ресемплинга.
        return ImageOps.flip(im)

    if t == "MIRROR_ROTATE_270":
        return ImageOps.mirror(im).transpose(Image.ROTATE_270)

    return im


# --------------- ЧТЕНИЕ JSON ---------------
_WHITESPACE = {" ", "\t", "\r", "\n"}


def _strip_trailing_commas(payload: str) -> str:
    """Удаляет завершающие запятые перед } или ] вне строк."""

    result: list[str] = []
    in_string = False
    escape = False

    for ch in payload:
        if in_string:
            result.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            result.append(ch)
            continue

        if ch in "]}":
            idx = len(result) - 1
            while idx >= 0 and result[idx] in _WHITESPACE:
                idx -= 1
            if idx >= 0 and result[idx] == ',':
                del result[idx]
            result.append(ch)
            continue

        result.append(ch)

    return "".join(result)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        payload = fh.read()

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        cleaned = _strip_trailing_commas(payload)
        if cleaned != payload:
            return json.loads(cleaned)
        raise


# --------------- ИНДЕКС ПО ХЭШУ ---------------
def index_sprites(directory: str) -> Dict[str, str]:
    print("📦 Индексируем изображения...")
    hash_to_path: Dict[str, str] = {}
    for fname in os.listdir(directory):
        if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        path = os.path.join(directory, fname)
        try:
            with Image.open(path) as im:
                digest = sha256_java_argb(im)
                hash_to_path[digest] = path
        except Exception as e:
            print(f"⚠️ Не удалось прочитать {fname}: {e}")
    print(f"✅ Индексировано {len(hash_to_path)} изображений.")
    return hash_to_path


# --------------- СБОРКА ОДНОГО КАДРА ---------------
def build_frame(
    frame_key: str,
    frames: Dict[str, dict],
    hash_to_path: Dict[str, str],
    *,
    transform_overrides: Optional[Dict[_TransformKey, Dict[str, str]]] = None,
) -> Image.Image:
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

        with Image.open(sprite_path) as sprite_img:
            sprite = sprite_img.convert("RGBA")

        # 1) crop из source в координатах исходного спрайта
        src = part["source"]
        crop = sprite.crop(
            (src["x"], src["y"], src["x"] + src["width"], src["y"] + src["height"])
        )

        # 2) применяем трансформацию
        transform_name = (part.get("transform", {}).get("name") or "NONE")
        transformed_crop = apply_transform(
            crop,
            transform_name,
            sprite_id=part.get("sprite_id"),
            sprite_hash=sprite_hash,
            overrides=transform_overrides,
        )
        final_crop = transformed_crop

        # 3) позиция: absolute_position
        pos_x = int(round(part["absolute_position"]["x"] - fb["x"]))
        pos_y = int(round(part["absolute_position"]["y"] - fb["y"]))

        # 4) накладываем с альфой
        canvas.paste(final_crop, (pos_x, pos_y), final_crop)

    return canvas


def trim_to_content(image: Image.Image) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    """Обрезает прозрачные поля, возвращает срез и bbox (x0, y0, x1, y1)."""

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        full_bbox = (0, 0, image.width, image.height)
        return image, full_bbox

    cropped = image.crop(bbox)
    return cropped, bbox


def export_gif(frames: List[Image.Image], durations: List[int], path: str) -> None:
    print("🎞️ Экспорт GIF …")
    first, *rest = frames
    first.save(
        path,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=0,
        disposal=2,
        transparency=0,
    )
    print(f"🎬 GIF сохранён: {path}")


@dataclass
class FrameData:
    key: str
    image: Image.Image
    trimmed: Image.Image
    bbox: Tuple[int, int, int, int]
    duration_ms: int


def assemble_frames(
    json_path: str,
    sprites_dir: str,
    *,
    transform_overrides: Optional[Dict[_TransformKey, Dict[str, str]]] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> List[FrameData]:
    data = load_json(json_path)

    frame_keys = data["meta"]["frame_keys"]
    frames = data["frames"]

    effective_overrides = _resolve_overrides(transform_overrides)
    hash_to_path = index_sprites(sprites_dir)

    assembled: List[FrameData] = []

    total = len(frame_keys)
    for idx, key in enumerate(frame_keys):
        print(f"🧩 Собираем {key} …")
        img = build_frame(key, frames, hash_to_path, transform_overrides=effective_overrides)

        trimmed, bbox = trim_to_content(img)
        duration = frames[key].get("duration_ms", 40)
        assembled.append(
            FrameData(
                key=key,
                image=img,
                trimmed=trimmed,
                bbox=bbox,
                duration_ms=duration,
            )
        )

        if progress:
            progress(idx + 1, total, key)

    print(f"✅ Собрано кадров: {len(assembled)}")
    if progress:
        progress(total, total, "")
    return assembled


def save_trimmed_frames(frames: List[FrameData], directory: str) -> None:
    os.makedirs(directory, exist_ok=True)
    for frame in frames:
        frame_path = os.path.join(directory, f"{frame.key}.png")
        frame.trimmed.save(frame_path)
    print(f"💾 Кадры сохранены в {directory}")


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    frames = assemble_frames(JSON_PATH, SPRITES_DIR)
    if not frames:
        print("❌ Нет кадров для экспорта.")
        return

    save_trimmed_frames(frames, OUTPUT_DIR)
    export_gif(
        [frame.image for frame in frames],
        [frame.duration_ms for frame in frames],
        GIF_PATH,
    )


if __name__ == "__main__":
    main()
