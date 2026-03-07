import json
import os
import random
import string
import io
from PIL import Image, ImageDraw

_DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")


def _load_json(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def _load_lines(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def random_string(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def random_nickname() -> str:
    data = _load_json("nicknames.json")
    template = random.randint(1, 5)

    if template == 1:
        # прилагательное + существительное
        t = data["template1"]
        adj = random.choice(t["adjectives"])
        noun = random.choice(t["nouns"])
        return f"{adj} {noun}"

    elif template == 2:
        # звание/роль + область
        t = data["template2"]
        role = random.choice(t["roles"])
        domain = random.choice(t["domains"])
        return f"{role} {domain}"

    elif template == 3:
        # одно мемное слово
        word = random.choice(data["template3"]["words"])
        if random.random() < 0.4:
            word += str(random.randint(1, 9999))
        return word

    elif template == 4:
        # мемная фраза (с подстановкой чисел)
        phrase = random.choice(data["template4"]["phrases"])
        n = random.choice([18, 19, 20, 21, 228, 322, 1337, 2003, 2005, 2007,
                           30, 50, 100, 150, 200, 300, 500, 666, 777, 1488])
        return phrase.replace("{n}", str(n))

    else:
        # кличка/имя + цифры
        name = random.choice(data["template5"]["names"])
        digits = random.choice([
            str(random.randint(0, 99)),
            str(random.randint(100, 999)),
            str(random.randint(1, 9999)),
            "228", "1337", "777", "666", "228",
            "2003", "2004", "2005", "2006", "2007",
            "007", "008", "013", "096", "174",
        ])
        return f"{name}{digits}"


def random_group_name() -> str:
    data = _load_json("group_names.json")
    suffix = random.randint(1, 999)
    return f"{random.choice(data['prefixes'])} {random.choice(data['words'])} {suffix}"


def random_group_abbreviation() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=random.randint(3, 6)))


def random_bio() -> str:
    bios = _load_lines("bios.txt")
    return random.choice(bios)


def generate_random_avatar(size: int = 184) -> bytes:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)

    style = random.choice(["gradient", "blocks", "circles", "noise"])

    if style == "gradient":
        c1 = tuple(random.randint(0, 255) for _ in range(3))
        c2 = tuple(random.randint(0, 255) for _ in range(3))
        for y in range(size):
            t = y / size
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            draw.line([(0, y), (size, y)], fill=(r, g, b))

    elif style == "blocks":
        block_size = random.choice([23, 46, 92])
        for x in range(0, size, block_size):
            for y in range(0, size, block_size):
                color = tuple(random.randint(0, 255) for _ in range(3))
                draw.rectangle([x, y, x + block_size, y + block_size], fill=color)

    elif style == "circles":
        bg = tuple(random.randint(0, 255) for _ in range(3))
        draw.rectangle([0, 0, size, size], fill=bg)
        for _ in range(random.randint(5, 20)):
            cx = random.randint(0, size)
            cy = random.randint(0, size)
            radius = random.randint(10, size // 2)
            color = tuple(random.randint(0, 255) for _ in range(3))
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=color,
            )

    elif style == "noise":
        pixels = img.load()
        for x in range(size):
            for y in range(size):
                pixels[x, y] = tuple(random.randint(0, 255) for _ in range(3))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
