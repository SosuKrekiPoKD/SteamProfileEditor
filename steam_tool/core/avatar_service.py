import os
import random

from core.steam_auth import SteamSession
from core.account_manager import Account

_AVATARS_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data", "avatars")


def _get_random_avatar_bytes() -> tuple:
    """Pick a random avatar image from the avatars pool.

    Falls back to generated avatar if no images found.
    Returns (filename, bytes, content_type).
    """
    if not os.path.isdir(_AVATARS_DIR):
        raise Exception("Avatar folder not found. Add .jpg/.png images to steam_tool/data/avatars/")

    files = [f for f in os.listdir(_AVATARS_DIR)
             if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    if not files:
        raise Exception("No avatar images found. Add .jpg/.png images to steam_tool/data/avatars/")

    chosen = random.choice(files)
    path = os.path.join(_AVATARS_DIR, chosen)
    with open(path, "rb") as f:
        data = f.read()

    ext = chosen.rsplit(".", 1)[-1].lower()
    ct = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    return chosen, data, ct


def set_random_avatar(session: SteamSession, account: Account, **kwargs) -> str:
    """Upload a random avatar to the Steam profile."""
    filename, avatar_bytes, content_type = _get_random_avatar_bytes()

    url = f"{session.BASE_URL}/actions/FileUploader"
    files = {
        "avatar": (filename, avatar_bytes, content_type),
    }
    data = {
        "type": "player_avatar_image",
        "sId": session.steam_id,
        "sessionid": session.session_id,
        "doSub": "1",
        "json": "1",
    }

    resp = session.post(url, data=data, files=files)
    if resp.status_code == 200:
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if result.get("success"):
            return "Avatar updated"
        if "success" in resp.text.lower() or resp.status_code == 200:
            return "Avatar uploaded"
    raise Exception(f"Avatar upload failed: {resp.status_code} {resp.text[:200]}")
