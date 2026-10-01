"""Small synthetic animation fixtures, with no user images or network locations."""

import io

from PIL import Image


def animation_bytes(kind="GIF", *, count=3, size=(6, 4), durations=None, poster=False):
    colors = ("red", "green", "blue", "yellow", "purple", "cyan", "white", "black", "orange", "pink")
    frames = [Image.new("RGBA", size, colors[i % len(colors)]) for i in range(count)]
    first = Image.new("RGBA", size, "gray") if poster else frames.pop(0)
    options = {"default_image": True} if poster else {}
    output = io.BytesIO()
    first.save(output, format=kind, save_all=True, append_images=frames,
               duration=durations if durations is not None else [40] * count, loop=0, lossless=True, **options)
    return output.getvalue()


def pixels(content):
    with Image.open(io.BytesIO(content)) as image:
        return image.convert("RGBA").getpixel((0, 0))
