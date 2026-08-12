"""Shared synthetic "aerial roof" image generator. Used by the mock imagery
provider so there's something real to segment/detect/diff against without a
real imagery vendor -- schematic, not photographic, and explicitly not meant
to be read as a real damage signal (see app/services/defects.py). Deterministic
per (seed, damage_marks) so repeat requests for the same building/year return
the same image, and different years produce different (comparable) images.
"""
import io
import random

from PIL import Image, ImageDraw

SIZE = 512


ROOF_FILL = (120, 92, 74)
# Texture lines (ridge, shingle courses) are intentionally close in color to
# ROOF_FILL -- low enough contrast that the rule-based detector's background
# thresholding (see app/services/defects.py) doesn't flag ordinary roof
# texture as an anomaly. No outline stroke is drawn around the rectangle at
# all: an outline sits exactly on the crop boundary that
# app/services/footprint.py's center-crop uses, and slicing through a
# high-contrast border there was producing spurious "defect" contours along
# the image edges -- a real bug the detector correctly caught once it was
# actually run against this fixture.
TEXTURE_COLOR = (104, 78, 62)
# Damage marks use high-contrast colors so they reliably exceed the
# detector's anomaly threshold regardless of exact background sampling.
DAMAGE_COLORS = [(200, 190, 170), (170, 160, 145), (40, 30, 25)]


def generate_schematic_roof(seed: int, num_damage_marks: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (SIZE, SIZE), (86, 125, 70))  # yard/grass background
    draw = ImageDraw.Draw(img)

    margin = 60
    draw.rectangle([margin, margin, SIZE - margin, SIZE - margin], fill=ROOF_FILL)
    draw.line([(margin, SIZE // 2), (SIZE - margin, SIZE // 2)], fill=TEXTURE_COLOR, width=3)
    for y in range(margin + 20, SIZE - margin, 22):
        draw.line([(margin, y), (SIZE - margin, y)], fill=TEXTURE_COLOR, width=1)

    for _ in range(num_damage_marks):
        x = rng.randint(margin + 10, SIZE - margin - 10)
        y = rng.randint(margin + 10, SIZE - margin - 10)
        r = rng.randint(3, 9)
        color = rng.choice(DAMAGE_COLORS)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

    return img


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
