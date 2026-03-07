from core.steam_auth import SteamSession
from core.account_manager import Account
from utils.helpers import generate_random_avatar


def set_random_avatar(session: SteamSession, account: Account, **kwargs) -> str:
    """Upload a random avatar to the Steam profile."""
    avatar_bytes = generate_random_avatar(184)

    url = f"{session.BASE_URL}/actions/FileUploader"
    files = {
        "avatar": ("avatar.png", avatar_bytes, "image/png"),
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
        # Some responses return HTML on success
        if "success" in resp.text.lower() or resp.status_code == 200:
            return "Avatar uploaded"
    raise Exception(f"Avatar upload failed: {resp.status_code} {resp.text[:200]}")
