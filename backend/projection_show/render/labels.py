"""Readable calibration labels, rasterized once and composited by the GPU."""

from PIL import Image, ImageDraw, ImageFont


def calibration_label(surface: dict, projector: dict) -> Image.Image:
    width, height = surface["logical"]["width"], surface["logical"]["height"]
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    size = max(10, min(90, width // 12, height // 12))
    font = ImageFont.load_default(size=size)
    title = surface["name"]
    while draw.textlength(title, font=font) > width * 0.8 and size > 8:
        size -= 1
        font = ImageFont.load_default(size=size)
    small = ImageFont.load_default(size=max(8, size * 0.48))
    center = (width / 2, height / 2)
    draw.rectangle((width * 0.08, height * 0.38, width * 0.92, height * 0.64), fill=(0, 0, 0, 200))
    draw.text((center[0], height * 0.46), title, font=font, fill="white", anchor="mm")
    draw.text(
        (center[0], height * 0.56),
        f"{projector['name']}  ·  {width} × {height}",
        font=small,
        fill="#c5e3d6",
        anchor="mm",
    )
    for i, (x, y) in enumerate(((0.05, 0.05), (0.95, 0.05), (0.95, 0.95), (0.05, 0.95)), start=1):
        draw.text(
            (width * x, height * y),
            str(i),
            font=small,
            fill="white",
            anchor="mm",
            stroke_width=2,
            stroke_fill="black",
        )
    return image
