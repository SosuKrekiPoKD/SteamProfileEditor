import random
import re
import json

from core.steam_auth import SteamSession
from core.account_manager import Account
from utils.helpers import random_nickname, random_bio


def randomize_profile(session: SteamSession, account: Account, **kwargs) -> str:
    """Randomize all editable profile fields using items from inventory."""
    changes = []

    # 1. Change profile name and bio
    name_result = _set_profile_info(session, **kwargs)
    if name_result:
        changes.append(name_result)

    # 2. Set random profile items from inventory (background, mini-profile, etc.)
    items_result = _set_random_profile_items(session)
    if items_result:
        changes.append(items_result)

    if not changes:
        return "No changes made (no items in inventory?)"
    return "; ".join(changes)


def change_profile_name(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_profile_info(session, change_name=True, change_bio=False)


def change_profile_bio(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_profile_info(session, change_name=False, change_bio=True)


def change_profile_background(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_random_profile_items(session, only_background=True)


def _set_profile_info(session: SteamSession, change_name: bool = True,
                      change_bio: bool = True, **kwargs) -> str:
    """Change profile name, bio, and other text fields."""
    # First get current profile edit page to extract existing values
    edit_url = f"{session.profile_url}/edit/info"
    resp = session.get(edit_url)
    if resp.status_code != 200:
        raise Exception(f"Failed to load profile edit page: {resp.status_code}")

    new_name = random_nickname() if change_name else ""
    new_bio = random_bio() if change_bio else ""

    # Extract existing values from page
    current_name = ""
    name_match = re.search(r'id="personaName"[^>]*value="([^"]*)"', resp.text)
    if name_match:
        current_name = name_match.group(1)

    data = {
        "sessionID": session.session_id,
        "type": "profileSave",
        "personaName": new_name if change_name else current_name,
        "real_name": "",
        "summary": new_bio if change_bio else "",
        "country": "",
        "state": "",
        "city": "",
        "customURL": "",
        "json": "1",
    }

    save_url = f"{session.profile_url}/edit"
    resp = session.post(save_url, data=data)

    parts = []
    if change_name:
        parts.append(f"Name → {new_name}")
    if change_bio:
        parts.append(f"Bio updated")

    if resp.status_code == 200:
        return ", ".join(parts)
    raise Exception(f"Profile save failed: {resp.status_code}")


def _set_random_profile_items(session: SteamSession,
                              only_background: bool = False) -> str:
    """Set random profile items (background, mini-profile, avatar frame) from inventory."""
    # Use the newer inventory API directly (old json API is unreliable)
    return _set_random_profile_items_new_api(session, only_background)


def _set_random_profile_items_new_api(session: SteamSession,
                                      only_background: bool = False) -> str:
    """Fallback using newer inventory API."""
    inventory_url = (
        f"https://steamcommunity.com/inventory/{session.steam_id}/753/6"
        f"?l=english&count=500"
    )
    resp = session.get(inventory_url)
    if resp.status_code != 200:
        return ""
    try:
        inv_data = resp.json()
    except Exception:
        return ""

    assets = inv_data.get("assets", [])
    descriptions = {
        (d["classid"], d.get("instanceid", "0")): d
        for d in inv_data.get("descriptions", [])
    }

    backgrounds = []
    mini_profiles = []
    avatar_frames = []

    for asset in assets:
        key = (asset["classid"], asset.get("instanceid", "0"))
        desc = descriptions.get(key, {})
        tags = {t.get("category"): t.get("internal_name", "") for t in desc.get("tags", [])}
        item_type = tags.get("item_class", "")

        entry = {"assetid": asset["assetid"], "desc": desc}
        if "item_class_4" in item_type:
            backgrounds.append(entry)
        elif "item_class_8" in item_type:
            mini_profiles.append(entry)
        elif "item_class_11" in item_type:
            avatar_frames.append(entry)

    changes = []

    if backgrounds:
        bg = random.choice(backgrounds)
        if _equip_profile_item(session, bg["assetid"], "profile_background"):
            changes.append(f"Background → {bg['desc'].get('name', '?')}")

    if not only_background:
        if mini_profiles:
            mp = random.choice(mini_profiles)
            if _equip_profile_item(session, mp["assetid"], "mini_profile_background"):
                changes.append(f"Mini profile → {mp['desc'].get('name', '?')}")
        if avatar_frames:
            af = random.choice(avatar_frames)
            if _equip_profile_item(session, af["assetid"], "avatar_frame"):
                changes.append(f"Avatar frame → {af['desc'].get('name', '?')}")

    return ", ".join(changes) if changes else ""


def _equip_profile_item(session: SteamSession, asset_id: str,
                        item_type: str) -> bool:
    """Equip a profile item (background, mini-profile, avatar frame)."""
    url = (
        f"https://api.steampowered.com/IPlayerService/SetEquippedProfileItemFlags/v1/"
    )
    # Use community endpoint instead
    url = f"{session.profile_url}/ajaxsetprofilebackground/"
    data = {
        "sessionid": session.session_id,
        "communityitemid": asset_id,
    }

    if item_type == "profile_background":
        url = f"{session.profile_url}/edit/background"
        data = {
            "sessionid": session.session_id,
            "profile_background[image_large]": asset_id,
            "json": "1",
        }
    elif item_type == "mini_profile_background":
        url = f"{session.profile_url}/edit/background"
        data = {
            "sessionid": session.session_id,
            "profile_background[mini_profile_background]": asset_id,
            "json": "1",
        }
    elif item_type == "avatar_frame":
        url = f"{session.profile_url}/edit/background"
        data = {
            "sessionid": session.session_id,
            "profile_background[avatar_frame]": asset_id,
            "json": "1",
        }

    resp = session.post(url, data=data)
    return resp.status_code == 200
