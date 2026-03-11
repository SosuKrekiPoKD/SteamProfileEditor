import json
import time
import threading

from core.steam_auth import SteamSession
from core.account_manager import Account


API_URL = "https://api.steampowered.com"


# community_item_class names for logging
ITEM_TYPE_NAMES = {
    3: "Profile Background",
    4: "Emoticon",
    8: "Profile Modifier",
    11: "Sticker",
    12: "Chat Effect",
    13: "Mini-Profile Background",
    14: "Avatar Frame",
    15: "Animated Avatar",
    16: "Steam Deck Keyboard Skin",
    20: "Startup Movie",
}

# Bundle types in the "type" field
BUNDLE_TYPES = {5, 6}


def claim_free_pointshop_items(session: SteamSession, account: Account, **kwargs) -> str:
    """Claim all free (0 points) items from the Steam Points Shop.

    Uses targeted queries (filters=[3] for events, filters=[1] for exclusives)
    instead of scanning 150k+ items. Includes free bundles which give multiple items.
    """
    _log = kwargs.get("log_callback") or (lambda m: None)

    if not session.access_token:
        raise Exception("No access_token — cannot access Points Shop API")

    # Step 1: Get free items (from cache or query)
    ps_cache = kwargs.get("_ps_cache")
    free_items = None

    if ps_cache is not None:
        with ps_cache["lock"]:
            if ps_cache["items"] is None:
                _log(f"[INFO] {account.username}: querying free Points Shop items...")
                ps_cache["items"] = _query_free_items(session, _log)
            free_items = ps_cache["items"]
    else:
        _log(f"[INFO] {account.username}: querying free Points Shop items...")
        free_items = _query_free_items(session, _log)

    if not free_items:
        _log(f"[INFO] {account.username}: no free items found in Points Shop")
        return "No free items available"

    _log(f"[INFO] {account.username}: found {len(free_items)} free item(s), claiming...")

    # Step 2: Redeem each free item (including bundles)
    claimed = 0
    already_owned = 0
    failed = 0

    for item in free_items:
        defid = item["defid"]
        name = item.get("_display_name", f"defid:{defid}")
        type_name = item.get("_type_name", "")
        is_bundle = item.get("_is_bundle", False)

        try:
            result = _redeem_item(session, defid, _log=_log)
            if result == "ok":
                claimed += 1
                bundle_label = " [BUNDLE]" if is_bundle else ""
                _log(f"[OK] {account.username}: claimed «{name}» ({type_name}){bundle_label}")
            elif result == "already_owned":
                already_owned += 1
            else:
                failed += 1
                _log(f"[FAIL] {account.username}: «{name}» — {result}")
        except Exception as e:
            failed += 1
            _log(f"[FAIL] {account.username}: «{name}» — {e}")

        time.sleep(0.3)

    _log(f"[INFO] {account.username}: Points Shop done — "
         f"claimed: {claimed}, already owned: {already_owned}, failed: {failed}")

    if claimed == 0 and already_owned == len(free_items):
        return f"All {len(free_items)} free items already owned"
    return f"Claimed {claimed}/{len(free_items)} free items ({already_owned} already owned, {failed} failed)"


def _query_free_items(session, _log):
    """Query the Points Shop for free items using targeted filters.

    Strategy:
    1. filters=[3] (Sales & Events) — ~161 items, contains free bundles
    2. filters=[1] (Points Shop Exclusive) — free stickers, avatars, etc.
    Both queries are small and fast (1-2 pages each).
    """
    url = f"{API_URL}/ILoyaltyRewardsService/QueryRewardItems/v1/"
    all_items = []
    seen_defids = set()

    # Query 1: Sales & Events (main source of free bundles)
    _log("  [INFO] Querying Sales & Events items (filters=3)...")
    events_items = _query_with_filter(session, url, filter_id=3, _log=_log)
    _log(f"  [INFO] Sales & Events: {len(events_items)} total items")

    for item in events_items:
        free_item = _check_free_item(item, seen_defids, include_bundles=True)
        if free_item:
            all_items.append(free_item)

    _log(f"  [INFO] Free from events: {len(all_items)} items")

    # Query 2: Points Shop Exclusive (free stickers, animated avatars, etc.)
    _log("  [INFO] Querying Points Shop Exclusive items (filters=1)...")
    exclusive_items = _query_with_filter(session, url, filter_id=1, _log=_log)
    _log(f"  [INFO] Points Shop Exclusive: {len(exclusive_items)} total items")

    count_before = len(all_items)
    for item in exclusive_items:
        free_item = _check_free_item(item, seen_defids, include_bundles=True)
        if free_item:
            all_items.append(free_item)

    _log(f"  [INFO] Free from exclusives: {len(all_items) - count_before} items")

    if all_items:
        _log(f"  [INFO] Total free items to claim: {len(all_items)}")
        for item in all_items:
            bundle_tag = " [BUNDLE]" if item.get("_is_bundle") else ""
            _log(f"    - {item['_display_name']} ({item['_type_name']}){bundle_tag}")

    return all_items


def _query_with_filter(session, url, filter_id, _log):
    """Query QueryRewardItems with a specific filter, paginating through all results."""
    all_definitions = []
    cursor = ""
    page = 0

    while True:
        page += 1
        input_data = {
            "count": 200,
            "language": "english",
            "filters": [filter_id],
            "include_direct_purchase_disabled": True,
        }
        if cursor:
            input_data["cursor"] = cursor

        params = {
            "access_token": session.access_token,
            "input_json": json.dumps(input_data),
        }

        try:
            resp = session.session.get(url, params=params, timeout=20)
        except Exception as e:
            _log(f"  [WARN] QueryRewardItems filter={filter_id} page {page} failed: {e}")
            break

        if resp.status_code != 200:
            _log(f"  [WARN] QueryRewardItems filter={filter_id} HTTP {resp.status_code}")
            break

        try:
            data = resp.json().get("response", {})
        except ValueError:
            _log(f"  [WARN] QueryRewardItems filter={filter_id} invalid JSON")
            break

        definitions = data.get("definitions", [])
        if not definitions:
            break

        all_definitions.extend(definitions)

        next_cursor = data.get("next_cursor", "")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

        if page >= 50:
            break

        time.sleep(0.2)

    return all_definitions


def _check_free_item(item, seen_defids, include_bundles=True):
    """Check if an item is free (point_cost == 0) and return enriched dict or None."""
    point_cost = item.get("point_cost", -1)
    if isinstance(point_cost, str):
        point_cost = int(point_cost) if point_cost.isdigit() else -1
    if point_cost != 0:
        return None

    defid = item.get("defid")
    if defid in seen_defids:
        return None
    seen_defids.add(defid)

    # Check active flag
    if item.get("active") is False:
        return None

    item_type = item.get("type", 0)
    if isinstance(item_type, str):
        item_type = int(item_type) if item_type.isdigit() else 0

    is_bundle = item_type in BUNDLE_TYPES
    if is_bundle and not include_bundles:
        return None

    # Build display name
    cid = item.get("community_item_data", {})
    name = (cid.get("item_name", "") or cid.get("item_title", "")
            or item.get("internal_description", "") or f"defid:{defid}")

    # Get community_item_class for type name
    community_class = item.get("community_item_class", 0)
    if isinstance(community_class, str):
        community_class = int(community_class) if community_class.isdigit() else 0
    type_name = ITEM_TYPE_NAMES.get(community_class, "")

    if is_bundle:
        type_name = "Bundle"
        # Count items in the bundle
        bundle_defids = item.get("bundle_defids", [])
        if bundle_defids:
            type_name = f"Bundle ({len(bundle_defids)} items)"

    if not type_name:
        type_name = f"type:{item_type}"

    # Return enriched item dict
    enriched = dict(item)
    enriched["_display_name"] = name
    enriched["_type_name"] = type_name
    enriched["_is_bundle"] = is_bundle
    return enriched


def _redeem_item(session, defid, _log=None):
    """Redeem a single free item via RedeemPoints.

    Uses input_json with proper integer types (matching protobuf definition).
    Falls back to direct form data if input_json fails.
    """
    url = f"{API_URL}/ILoyaltyRewardsService/RedeemPoints/v1/"

    # Method 1: input_json as URL param
    redeem_data = {"defid": int(defid), "expected_points_cost": 0}
    try:
        resp = session.session.post(
            url,
            params={
                "access_token": session.access_token,
                "input_json": json.dumps(redeem_data),
            },
            data={},
            timeout=15,
        )
    except Exception as e:
        raise Exception(f"RedeemPoints request failed: {e}")

    try:
        body = resp.json()
    except ValueError:
        body = {}

    result = body.get("response", {})
    eresult = body.get("eresult")

    if _log:
        _log(f"  [DEBUG] RedeemPoints defid={defid}: HTTP {resp.status_code}, "
             f"eresult={eresult}, body={json.dumps(body, ensure_ascii=False)[:200]}")

    # Success — got a community item ID or bundle IDs
    if resp.status_code == 200 and (result.get("communityitemid") or result.get("bundle_community_item_ids")):
        return "ok"

    # Already owned (eresult 29 = DuplicateRequest)
    if eresult == 29:
        return "already_owned"

    # HTTP 500 with empty body usually means already owned
    if resp.status_code == 500:
        return "already_owned"

    # 200 with empty response — try fallback with direct form data
    if resp.status_code == 200 and not result:
        return _redeem_item_fallback(session, defid, _log)

    # Other error
    error_msg = body.get("message", "") or resp.text[:200]
    if "already" in error_msg.lower():
        return "already_owned"
    if "not enough" in error_msg.lower() or "insufficient" in error_msg.lower():
        return "not_free"

    return f"error: HTTP {resp.status_code}, eresult={eresult}"


def _redeem_item_fallback(session, defid, _log=None):
    """Fallback: try RedeemPoints with direct form fields (old method)."""
    url = (f"{API_URL}/ILoyaltyRewardsService/RedeemPoints/v1/"
           f"?access_token={session.access_token}")

    data = {"defid": str(defid), "expected_points_cost": "0"}

    try:
        resp = session.session.post(url, data=data, timeout=15)
    except Exception:
        return "skipped"

    try:
        body = resp.json()
    except ValueError:
        body = {}

    result = body.get("response", {})
    eresult = body.get("eresult")

    if _log:
        _log(f"  [DEBUG] RedeemPoints fallback defid={defid}: HTTP {resp.status_code}, "
             f"eresult={eresult}, body={json.dumps(body, ensure_ascii=False)[:200]}")

    if resp.status_code == 200 and (result.get("communityitemid") or result.get("bundle_community_item_ids")):
        return "ok"

    if eresult == 29 or resp.status_code == 500:
        return "already_owned"

    return "already_owned"  # empty 200 after both methods = already owned
