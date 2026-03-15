import random
import time

from core.steam_auth import SteamSession
from core.account_manager import Account
from utils.helpers import random_review


API_URL = "https://api.steampowered.com"
STORE_URL = "https://store.steampowered.com"
EXCLUDED_APPIDS = {730}  # CS2


def leave_random_review(session: SteamSession, account: Account, **kwargs) -> str:
    """Leave a review on a random game from the account's library."""
    _log = kwargs.get("log_callback") or (lambda m: None)

    if not session.access_token:
        raise Exception("No access_token — cannot access Steam API")

    # Step 1: Get owned games
    games = _get_owned_games(session)

    if not games:
        _log(f"[INFO] {account.username}: no games in library")
        return "No games in library"

    _log(f"[INFO] {account.username}: found {len(games)} game(s) in library")

    # Step 2: Ensure store.steampowered.com session cookie
    store_session_id = _ensure_store_session(session, _log)

    # Step 3: Try games until we successfully leave a review
    games = [g for g in games if g["appid"] not in EXCLUDED_APPIDS]
    if not games:
        _log(f"[INFO] {account.username}: no eligible games (all excluded)")
        return "No eligible games"

    random.shuffle(games)
    max_attempts = min(len(games), 10)

    for game in games[:max_attempts]:
        appid = game["appid"]
        name = game.get("name", f"AppID {appid}")

        review_text, is_positive = random_review()

        try:
            result = _submit_review(
                session, store_session_id, appid, review_text, is_positive, _log
            )
            if result == "ok":
                sentiment = "positive" if is_positive else "negative"
                _log(f"[OK] {account.username}: reviewed «{name}» ({sentiment}): {review_text}")
                return f"Reviewed «{name}» ({sentiment})"
            elif result == "already_reviewed":
                _log(f"  [SKIP] {account.username}: «{name}» already reviewed")
                continue
            elif result == "not_owned":
                _log(f"  [SKIP] {account.username}: «{name}» cannot review (not owned/free)")
                continue
            else:
                _log(f"  [WARN] {account.username}: «{name}» review failed: {result}")
                continue
        except Exception as e:
            _log(f"  [WARN] {account.username}: «{name}» review error: {e}")
            continue

    raise Exception(f"Could not review any of {max_attempts} games (already reviewed or errors)")


def _get_owned_games(session: SteamSession) -> list:
    """Get list of owned games via IPlayerService API."""
    import json

    url = f"{API_URL}/IPlayerService/GetOwnedGames/v1/"
    params = {
        "access_token": session.access_token,
        "input_json": json.dumps({
            "steamid": str(session.steam_id),
            "include_appinfo": True,
            "include_played_free_games": False,
        }),
    }

    try:
        resp = session.session.get(url, params=params, timeout=15)
    except Exception as e:
        raise Exception(f"GetOwnedGames request failed: {e}")

    if resp.status_code != 200:
        raise Exception(f"GetOwnedGames HTTP {resp.status_code}")

    try:
        data = resp.json().get("response", {})
    except ValueError:
        raise Exception("GetOwnedGames invalid JSON")

    return data.get("games", [])


def _ensure_store_session(session: SteamSession, _log) -> str:
    """Ensure we have a valid sessionid cookie for store.steampowered.com."""
    # Check existing cookies
    for c in session.session.cookies:
        if c.name == "sessionid" and "store.steampowered" in (c.domain or ""):
            return c.value

    # Visit store to establish sessionid cookie
    try:
        session.session.get(STORE_URL, timeout=15, allow_redirects=True)
    except Exception:
        pass

    for c in session.session.cookies:
        if c.name == "sessionid" and "store.steampowered" in (c.domain or ""):
            return c.value

    # Fallback: use community sessionid
    _log(f"  [WARN] Could not get store sessionid, using community sessionid")
    return session.session_id


def _submit_review(session, store_session_id, appid, comment, rated_up, _log) -> str:
    """Submit a review via the store endpoint."""
    url = f"{STORE_URL}/friends/recommendgame"

    data = {
        "appid": str(appid),
        "sessionid": store_session_id,
        "comment": comment,
        "rated_up": "true" if rated_up else "false",
        "is_public": "true",
        "language": "english",
        "received_compensation": "0",
    }

    headers = {
        "Referer": f"{STORE_URL}/app/{appid}/",
        "Origin": STORE_URL,
    }

    try:
        resp = session.session.post(url, data=data, headers=headers, timeout=15)
    except Exception as e:
        raise Exception(f"Review request failed: {e}")

    if resp.status_code != 200:
        text_lower = resp.text.lower()
        if "already" in text_lower or "update" in text_lower:
            return "already_reviewed"
        raise Exception(f"HTTP {resp.status_code}")

    # Parse JSON response
    try:
        result = resp.json()
        if result.get("success") in (True, 1, "1"):
            return "ok"
        if result.get("strError"):
            err = result["strError"].lower()
            if "already" in err or "update" in err:
                return "already_reviewed"
            if "own" in err or "purchase" in err:
                return "not_owned"
            return f"error: {result['strError']}"
    except (ValueError, AttributeError):
        pass

    # HTML fallback
    text_lower = resp.text.lower()
    if "success" in text_lower:
        return "ok"
    if "already" in text_lower:
        return "already_reviewed"

    return f"unknown response: {resp.text[:200]}"
