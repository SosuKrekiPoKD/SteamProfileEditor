import random
import string
import io
from PIL import Image, ImageDraw


def random_string(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def random_nickname() -> str:
    adjectives = [
        "Shadow", "Dark", "Neon", "Cyber", "Toxic", "Frost", "Storm", "Blaze",
        "Ghost", "Iron", "Pixel", "Rapid", "Silent", "Crimson", "Azure", "Void",
        "Omega", "Alpha", "Nova", "Lunar", "Solar", "Mystic", "Rogue", "Elite",
    ]
    nouns = [
        "Wolf", "Eagle", "Hawk", "Viper", "Knight", "Ninja", "Samurai", "Hunter",
        "Reaper", "Phantom", "Dragon", "Tiger", "Panther", "Cobra", "Falcon",
        "Spartan", "Titan", "Phoenix", "Raven", "Scorpion", "Demon", "Angel",
    ]
    number = random.randint(0, 9999)
    return f"{random.choice(adjectives)}{random.choice(nouns)}{number}"


def random_group_name() -> str:
    prefixes = [
        "Official", "The", "Team", "Clan", "Pro", "Elite", "United", "Global",
        "Supreme", "Ultimate", "Royal", "Prime", "Apex", "Top", "Best",
    ]
    words = [
        "Gamers", "Warriors", "Legends", "Champions", "Masters", "Heroes",
        "Titans", "Knights", "Phantoms", "Guardians", "Reapers", "Wolves",
        "Dragons", "Eagles", "Vipers", "Spartans", "Ninjas", "Hunters",
    ]
    suffix = random.randint(1, 999)
    return f"{random.choice(prefixes)} {random.choice(words)} {suffix}"


def random_group_abbreviation() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=random.randint(3, 6)))


def random_bio() -> str:
    bios = [
        "Just a gamer.", "Playing games since forever.", "GG WP.",
        "No time to explain.", "Achievement hunter.", "Casual player.",
        "Looking for teammates.", "Steam enthusiast.", "Game collector.",
        "Pro gamer wannabe.", "Just vibing.", "Don't add me if you're toxic.",
    ]
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
