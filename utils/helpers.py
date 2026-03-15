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
        t = data["template1"]
        adj = random.choice(t["adjectives"])
        noun = random.choice(t["nouns"])
        nick = f"{adj} {noun}"

    elif template == 2:
        t = data["template2"]
        role = random.choice(t["roles"])
        domain = random.choice(t["domains"])
        nick = f"{role} {domain}"

    elif template == 3:
        word = random.choice(data["template3"]["words"])
        if random.random() < 0.4:
            word += str(random.randint(1, 9999))
        nick = word

    elif template == 4:
        phrase = random.choice(data["template4"]["phrases"])
        n = random.choice([18, 19, 20, 21, 228, 322, 1337, 2003, 2005, 2007,
                           30, 50, 100, 150, 200, 300, 500, 666, 777, 1488])
        nick = phrase.replace("{n}", str(n))

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
        nick = f"{name}{digits}"

    # Steam requires 2-32 characters
    if len(nick) > 32:
        nick = nick[:32].rstrip()
    return nick


def random_group_name() -> str:
    data = _load_json("group_names.json")
    template = random.randint(1, 6)

    if template == 1:
        # RU: Бешеный Компот
        name = f"{random.choice(data['t1_adj'])} {random.choice(data['t1_noun'])}"
    elif template == 2:
        # RU: Секта Кабачков
        name = f"{random.choice(data['t2_type'])} {random.choice(data['t2_noun'])}"
    elif template == 3:
        # RU: Дно Общества 228
        name = f"{random.choice(data['t3_phrase'])} {random.choice(data['t3_number'])}"
    elif template == 4:
        # EN: Toxic Spoon Gang
        name = (f"{random.choice(data['t4_adj'])} {random.choice(data['t4_noun'])} "
                f"{random.choice(data['t4_suffix'])}")
    elif template == 5:
        # EN: Sigma Goblins
        name = f"{random.choice(data['t5_prefix'])} {random.choice(data['t5_word'])}"
    else:
        # X vs Y: Бобры vs Шаурма
        words = data["t6_word"]
        w1 = random.choice(words)
        w2 = random.choice(words)
        while w2 == w1:
            w2 = random.choice(words)
        name = f"{w1} vs {w2}"

    if len(name) > 64:
        name = name[:64].rstrip()
    return name


def random_group_abbreviation() -> str:
    length = random.randint(8, 12)
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def random_review(positive: bool = None) -> tuple:
    """Generate a random short review text. Returns (text, is_positive)."""
    data = _load_json("review_templates.json")

    if positive is None:
        positive = random.random() < 0.6  # 60% positive

    pool = data["positive"] if positive else data["negative"]
    template = random.randint(1, 3)

    if template == 1:
        text = random.choice(pool["t1_short"])
    elif template == 2:
        tmpl = random.choice(pool["t2_template"])
        text = tmpl.replace("{hours}", random.choice(pool["t2_hours"]))
        text = text.replace("{verdict}", random.choice(pool["t2_verdict"]))
    else:
        text = f"{random.choice(pool['t3_prefix'])} {random.choice(pool['t3_suffix'])}"

    return text, positive


_bio_generator = None

def random_bio() -> str:
    global _bio_generator
    if _bio_generator is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bio_generator",
            os.path.join(_DATA_DIR, "bio_generator.py"),
        )
        _bio_generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_bio_generator)
    return _bio_generator.generate_bio()


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
