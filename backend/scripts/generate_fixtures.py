"""One-off script to (re)generate the placeholder "aerial roof" fixture
images checked into backend/fixtures/sample_roofs/. These stand in for real
aerial imagery in mock mode -- they are schematic, not photographs, and exist
only so the vision pipeline (including the real Claude vision provider, when
VISION_PROVIDER=claude) has something to look at without a real imagery
vendor.

Requires Pillow (`pip install Pillow`) -- Pillow is NOT an app runtime
dependency, only needed to run this script. Re-run after editing:

    python scripts/generate_fixtures.py
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sample_roofs"
SIZE = 512

VARIANTS = {
    "roof_pristine": 0,
    "roof_light_damage": 12,
    "roof_moderate_damage": 40,
    "roof_severe_damage": 90,
}


def draw_roof(num_damage_marks: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (SIZE, SIZE), (86, 125, 70))  # yard/grass background
    draw = ImageDraw.Draw(img)

    # Roof footprint: an off-center rectangle with a gable ridge line, viewed
    # from directly above, roughly how a satellite/drone frame would look.
    margin = 60
    draw.rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        fill=(120, 92, 74),
        outline=(60, 45, 36),
        width=4,
    )
    draw.line([(margin, SIZE // 2), (SIZE - margin, SIZE // 2)], fill=(60, 45, 36), width=3)
    # Shingle course lines
    for y in range(margin + 20, SIZE - margin, 22):
        draw.line([(margin, y), (SIZE - margin, y)], fill=(104, 78, 62), width=1)

    # Damage marks: hail hits / missing-shingle patches as light speckles.
    for _ in range(num_damage_marks):
        x = rng.randint(margin + 10, SIZE - margin - 10)
        y = rng.randint(margin + 10, SIZE - margin - 10)
        r = rng.randint(3, 9)
        color = rng.choice([(200, 190, 170), (150, 110, 80), (170, 160, 145)])
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i, (name, marks) in enumerate(VARIANTS.items()):
        img = draw_roof(marks, seed=i)
        img.save(OUT_DIR / f"{name}.png")
        print(f"wrote {OUT_DIR / f'{name}.png'}")


if __name__ == "__main__":
    main()
