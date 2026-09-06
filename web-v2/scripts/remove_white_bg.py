"""Chroma-key white background removal using actual corner color.

Better than naive '255 - min(R,G,B)': keyed on the real background color
sampled from the corners, so JPEG-style noise in the original white gets
removed but the parrot / cart edges stay feathered.
"""
from PIL import Image, ImageChops

SRC = r"D:/ShoppingClaw/web-v2/src/assets/parrot-logo.png"

img = Image.open(SRC).convert("RGBA")
w, h = img.size

# Sample background color from all four corners (avg per channel)
samples = [img.getpixel((x, y))[:3] for (x, y) in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
bg = tuple(int(sum(s[i] for s in samples) / 4) for i in range(3))
print(f"sampled background (avg of corners): {bg}")

r, g, b, _ = img.split()

# Per-channel absolute difference from sampled bg
flat_r = Image.new("L", img.size, bg[0])
flat_g = Image.new("L", img.size, bg[1])
flat_b = Image.new("L", img.size, bg[2])
dr = ImageChops.difference(r, flat_r)
dg = ImageChops.difference(g, flat_g)
db = ImageChops.difference(b, flat_b)

# Per-pixel max across channels (ImageChops.lighter = max)
max_diff = ImageChops.lighter(ImageChops.lighter(dr, dg), db)

# Map distance -> alpha with fuzz threshold + linear ramp + clamp
fuzz, far = 18, 220
lut = [0 if i < fuzz else (255 if i > far else int((i - fuzz) * 255 / (far - fuzz))) for i in range(256)]
alpha = max_diff.point(lut)

out = Image.merge("RGBA", (r, g, b, alpha))
out.save(SRC, "PNG", optimize=True)

hist = alpha.histogram()
total = w * h
print(f"size {w}x{h}, total {total} px")
print(f"fully transparent (alpha=0):  {hist[0]:>8} ({hist[0]/total*100:.1f}%)")
print(f"fully opaque    (alpha=255): {hist[255]:>8} ({hist[255]/total*100:.1f}%)")
print(f"feathered edges  (1..254):    {total - hist[0] - hist[255]:>8}")