import html as html_mod
import random
import re
import json

from core.steam_auth import SteamSession
from core.account_manager import Account
from utils.helpers import random_nickname, random_bio


API_URL = "https://api.steampowered.com"

# API endpoint for each equippable item type
EQUIP_ENDPOINTS = {
    "profile_background": "SetProfileBackground",
    "mini_profile_background": "SetMiniProfileBackground",
    "avatar_frame": "SetAvatarFrame",
    "animated_avatar": "SetAnimatedAvatar",
}


def change_profile_name(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_profile_info(session, change_name=True, change_bio=False)


def change_profile_bio(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_profile_info(session, change_name=False, change_bio=True)


def change_profile_name_and_bio(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_profile_info(session, change_name=True, change_bio=True)


def set_random_background(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_random_item(session, "profile_background")


def set_random_mini_profile(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_random_item(session, "mini_profile_background")


def set_random_avatar_frame(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_random_item(session, "avatar_frame")


def set_random_animated_avatar(session: SteamSession, account: Account, **kwargs) -> str:
    return _set_random_item(session, "animated_avatar")


# ---------- Internal ----------

def _get_current_persona_name(session: SteamSession) -> str:
    """Get current persona name via Steam API (reliable, no HTML scraping)."""
    url = f"{API_URL}/ISteamUser/GetPlayerSummaries/v2/"
    try:
        resp = session.session.get(
            url,
            params={"access_token": session.access_token,
                    "steamids": session.steam_id},
            timeout=10,
        )
        if resp.status_code == 200:
            players = resp.json().get("response", {}).get("players", [])
            if players:
                return players[0].get("personaname", "")
    except Exception:
        pass
    # Fallback: try to extract from profile edit page
    try:
        edit_url = f"{session.profile_url}/edit/info"
        resp = session.get(edit_url)
        if resp.status_code == 200:
            import re
            for pattern in [
                r'"strPersonaName"\s*:\s*"([^"]*)"',
                r'id="personaName"[^>]*value="([^"]*)"',
                r'name="personaName"[^>]*value="([^"]*)"',
            ]:
                m = re.search(pattern, resp.text)
                if m and m.group(1):
                    return m.group(1)
    except Exception:
        pass
    return ""


def _set_profile_info(session: SteamSession, change_name: bool = True,
                      change_bio: bool = True, **kwargs) -> str:
    """Change profile name, bio, and other text fields."""
    log_cb = kwargs.get("log_callback")

    # Visit profile edit page — required for CSRF/session validation
    edit_url = f"{session.profile_url}/edit/info"
    edit_resp = session.get(edit_url)
    if edit_resp.status_code != 200:
        raise Exception(f"Failed to load profile edit page: {edit_resp.status_code}")

    page = edit_resp.text

    # Use sessionid from cookies (may differ from login-time value)
    session_id = session.session_id
    for c in session.session.cookies:
        if c.name == "sessionid" and "steamcommunity" in (c.domain or ""):
            session_id = c.value
            break

    # Extract current values from profile edit config
    current_name = ""
    current_bio = ""
    current_custom_url = ""

    # Parse data-profile-edit attribute (HTML-encoded JSON)
    m = re.search(r'data-profile-edit="([^"]*)"', page)
    if m:
        try:
            config = json.loads(html_mod.unescape(m.group(1)))
            current_name = config.get("strPersonaName", "")
            current_bio = config.get("strSummary", "")
            current_custom_url = config.get("strCustomURL", "")
        except (ValueError, KeyError):
            pass

    # Fallback: try g_rgProfileData JS variable
    if not current_name:
        m = re.search(r'g_rgProfileData\s*=\s*(\{.*?\});', page)
        if m:
            try:
                current_name = json.loads(m.group(1)).get("personaname", "")
            except (ValueError, KeyError):
                pass

    # If couldn't find name and we need to preserve it, try API
    if not current_name and not change_name:
        current_name = _get_current_persona_name(session)
    if not current_name and not change_name:
        current_name = session.username

    new_name = random_nickname() if change_name else current_name
    new_bio = random_bio() if change_bio else current_bio

    data = {
        "sessionID": session_id,
        "type": "profileSave",
        "personaName": new_name,
        "real_name": "",
        "headline": "",
        "summary": new_bio,
        "country": "",
        "state": "",
        "city": "",
        "customURL": current_custom_url,
        "json": "1",
    }

    save_url = f"{session.profile_url}/edit"
    resp = session.post(save_url, data=data)

    if log_cb:
        log_cb(f"  [DEBUG] Profile save: HTTP {resp.status_code}, body={resp.text[:300]}")

    if resp.status_code != 200:
        raise Exception(f"Profile save failed: HTTP {resp.status_code}")

    success = None
    try:
        result = resp.json()
        success = result.get("success")
    except (ValueError, AttributeError):
        if "error" in resp.text[:500].lower():
            raise Exception("Profile save returned error page")

    # success:1 — all good
    if success == 1 or success == "1":
        parts = []
        if change_name:
            parts.append(f"Name → {new_name}")
        if change_bio:
            parts.append(f"Bio updated")
        return ", ".join(parts)

    # success:2 — partial, verify what actually changed
    import time as _time
    _time.sleep(1)
    verify_resp = session.get(f"{session.profile_url}/edit/info")
    saved_name = ""
    saved_bio = ""
    mv = re.search(r'data-profile-edit="([^"]*)"', verify_resp.text)
    if mv:
        try:
            vcfg = json.loads(html_mod.unescape(mv.group(1)))
            saved_name = vcfg.get("strPersonaName", "")
            saved_bio = vcfg.get("strSummary", "")
        except (ValueError, KeyError):
            pass

    # Name: check it changed from what it was (Steam may truncate/filter)
    name_ok = (not change_name) or (saved_name != current_name)
    bio_ok = (not change_bio) or (saved_bio == new_bio)

    if name_ok and bio_ok:
        parts = []
        if change_name:
            parts.append(f"Name → {saved_name or new_name}")
        if change_bio:
            parts.append(f"Bio updated")
        return ", ".join(parts)

    if name_ok and not bio_ok:
        if change_name:
            raise Exception(f"Bio change failed (name changed to {saved_name})")
        else:
            raise Exception("Bio change failed")

    if not name_ok and bio_ok:
        raise Exception("Name change failed")

    raise Exception("Name and Bio change failed")


def _get_owned_profile_items(session: SteamSession) -> dict:
    """Get ALL owned equippable profile items via IPlayerService API.

    This returns items from Points Shop, events, and inventory — everything
    that can be equipped on a profile. Much more reliable than inventory scraping.
    """
    url = f"{API_URL}/IPlayerService/GetProfileItemsOwned/v1/"
    try:
        resp = session.session.get(
            url,
            params={"access_token": session.access_token, "language": "english"},
            timeout=15,
        )
    except Exception as e:
        raise Exception(f"GetProfileItemsOwned failed: {e}")

    if resp.status_code != 200:
        raise Exception(f"GetProfileItemsOwned HTTP {resp.status_code}")

    try:
        data = resp.json().get("response", {})
    except ValueError:
        raise Exception("GetProfileItemsOwned invalid JSON")

    items = {
        "profile_background": [],
        "mini_profile_background": [],
        "avatar_frame": [],
        "animated_avatar": [],
    }

    # Each category is a list in the response
    for item in data.get("profile_backgrounds", []):
        items["profile_background"].append({
            "communityitemid": str(item.get("communityitemid", "")),
            "name": item.get("name") or item.get("item_title") or "?",
        })

    for item in data.get("mini_profile_backgrounds", []):
        items["mini_profile_background"].append({
            "communityitemid": str(item.get("communityitemid", "")),
            "name": item.get("name") or item.get("item_title") or "?",
        })

    for item in data.get("avatar_frames", []):
        items["avatar_frame"].append({
            "communityitemid": str(item.get("communityitemid", "")),
            "name": item.get("name") or item.get("item_title") or "?",
        })

    for item in data.get("animated_avatars", []):
        items["animated_avatar"].append({
            "communityitemid": str(item.get("communityitemid", "")),
            "name": item.get("name") or item.get("item_title") or "?",
        })

    return items


def _set_random_item(session: SteamSession, item_type: str) -> str:
    """Pick a random item of the given type from owned items and equip it."""
    items = _get_owned_profile_items(session)
    candidates = items.get(item_type, [])

    type_label = item_type.replace("_", " ").title()

    if not candidates:
        return f"No {type_label} items owned"

    chosen = random.choice(candidates)
    ok = _equip_profile_item(session, chosen["communityitemid"], item_type)

    if ok:
        return f"{type_label} → {chosen['name']}"
    else:
        raise Exception(f"Failed to equip {type_label}: {chosen['name']}")


def _equip_profile_item(session: SteamSession, communityitemid: str,
                        item_type: str) -> bool:
    """Equip a profile item via IPlayerService API."""
    method = EQUIP_ENDPOINTS.get(item_type)
    if not method:
        return False

    url = f"{API_URL}/IPlayerService/{method}/v1/"
    resp = session.session.post(
        url,
        data={
            "access_token": session.access_token,
            "communityitemid": str(communityitemid),
        },
        timeout=15,
    )
    return resp.status_code == 200
