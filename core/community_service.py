import os
import random
import re
import time
import threading

from core.steam_auth import SteamSession
from core.account_manager import Account
from utils.helpers import (
    random_group_name,
    random_group_abbreviation,
    generate_random_avatar,
)

_DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_random_communities(session: SteamSession, account: Account,
                              min_count: int = 1, max_count: int = 1,
                              log_callback=None, **kwargs) -> str:
    """Create a random number of Steam groups (between min_count and max_count)."""
    _log = log_callback or (lambda m: None)
    count = random.randint(min_count, max_count)
    _log(f"[INFO] {account.username}: creating {count} group(s) (range {min_count}-{max_count})")
    created = []
    for i in range(count):
        if i > 0:
            time.sleep(random.uniform(2.0, 5.0))  # cooldown between creations
        # Retry up to 3 times with different names
        success = False
        for attempt in range(3):
            try:
                name = _create_one_group(session, _log)
                created.append(name)
                _log(f"[OK] {account.username}: Created group #{i+1}: {name}")
                success = True
                break
            except Exception as e:
                if attempt < 2 and "retrying" in str(e).lower():
                    _log(f"  [RETRY] {account.username}: group #{i+1} attempt {attempt+1}: {e}")
                    time.sleep(1)
                else:
                    _log(f"[FAIL] {account.username}: Create group #{i+1}: {e}")
                    break
    if not created:
        raise Exception("Could not create any groups (account may be limited)")
    return f"Created {len(created)}/{count} group(s)"


def join_random_communities(session: SteamSession, account: Account,
                            min_count: int = 1, max_count: int = 1,
                            used_groups: set = None,
                            log_callback=None, **kwargs) -> str:
    """Join a random number of unique Steam groups (between min_count and max_count)."""
    _log = log_callback or (lambda m: None)
    if used_groups is None:
        used_groups = set()

    count = random.randint(min_count, max_count)
    _log(f"[INFO] {account.username}: joining {count} group(s) (range {min_count}-{max_count})")

    joined = []
    candidates = _get_candidate_groups(session, _log, pool_size=max(count * 3, 30))
    random.shuffle(candidates)

    consecutive_session_errors = 0
    max_session_errors = 3  # abort if session is broken

    for group_name, group_url in candidates:
        if len(joined) >= count:
            break

        normalized = group_name.lower()
        if normalized in used_groups:
            continue

        try:
            result = _join_one_group(session, group_name, group_url, _log)
            consecutive_session_errors = 0  # reset on any non-session-error

            if result == "already_member":
                _log(f"  [SKIP] {group_name}: already a member")
                used_groups.add(normalized)
                continue
            if result in ("restricted", "full", "broken"):
                reasons = {"restricted": "invite-only", "full": "full/max pending",
                           "broken": "broken/unavailable"}
                _log(f"  [SKIP] {group_name}: {reasons[result]} — removed from pool")
                _remove_from_pool(normalized)
                continue
            joined.append(group_name)
            used_groups.add(normalized)
            _log(f"[OK] {account.username}: Joined group #{len(joined)}: {group_name}")
        except Exception as e:
            err_str = str(e).lower()
            if "session key" in err_str or "form session" in err_str:
                consecutive_session_errors += 1
                if consecutive_session_errors >= max_session_errors:
                    raise Exception(
                        f"Session is broken (invalid session key {consecutive_session_errors}x in a row)"
                    )
                continue  # don't log every single one
            consecutive_session_errors = 0
            _log(f"[FAIL] {account.username}: Join {group_name}: {e}")

    if not joined:
        raise Exception("Could not join any groups")
    return f"Joined {len(joined)}/{count} group(s)"


# ---------------------------------------------------------------------------
# Internal: create group
# ---------------------------------------------------------------------------

def _create_one_group(session, _log):
    """Create a single group. Returns group name on success, raises on failure."""
    group_name = random_group_name()
    abbreviation = random_group_abbreviation()

    create_url = f"{session.BASE_URL}/actions/GroupCreate"

    # Visit the create page first
    page_resp = session.session.get(create_url, timeout=15)
    if page_resp.status_code != 200:
        raise Exception(f"Cannot access create page: HTTP {page_resp.status_code}")

    # Check for error page
    title_m = re.search(r'<title>([^<]+)</title>', page_resp.text)
    title = title_m.group(1).strip() if title_m else ""
    if "Ошибка" in title or "Error" in title:
        raise Exception("Cannot access group creation page")

    # POST with correct field names:
    # groupName, abbreviation, groupLink, bIsPublic, sessionID, step
    data = {
        "sessionID": session.session_id,
        "step": "1",
        "groupName": group_name,
        "abbreviation": abbreviation,
        "groupLink": abbreviation,
        "bIsPublic": "1",
    }
    headers = {
        "Referer": create_url,
        "Origin": session.BASE_URL,
    }

    resp = session.session.post(create_url, data=data, headers=headers,
                                allow_redirects=True, timeout=15)

    _log(f"  [DEBUG] Create POST: HTTP {resp.status_code}, URL: {resp.url}")

    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}")

    # Success = redirected to the new group page
    if "/groups/" in resp.url and "GroupCreate" not in resp.url:
        try:
            _upload_group_avatar(session, resp.url)
        except Exception:
            pass
        return f"{group_name} ({abbreviation})"

    # Check for step 2 form (step 1 accepted, need to confirm)
    step_match = re.search(r'name="step"[^>]*value="(\d+)"', resp.text, re.I)
    if step_match:
        step_val = step_match.group(1)

        if step_val == "1":
            # Step 1 returned again — validation failed (name/url taken or other error)
            raise Exception("Group name or URL may be taken, retrying with different name")

        # Step 2+ — extract all fields (hidden inputs carry the group info)
        _log(f"  [DEBUG] Got step {step_val} form, submitting...")
        form_fields = re.findall(
            r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"',
            resp.text, re.I
        )
        data2 = {fn: fv for fn, fv in form_fields}
        data2["sessionID"] = session.session_id
        _log(f"  [DEBUG] Step {step_val} data: {data2}")

        resp2 = session.session.post(create_url, data=data2, headers=headers,
                                     allow_redirects=True, timeout=15)
        _log(f"  [DEBUG] Step {step_val} response: HTTP {resp2.status_code}, URL: {resp2.url}")

        if "/groups/" in resp2.url and "GroupCreate" not in resp2.url:
            try:
                _upload_group_avatar(session, resp2.url)
            except Exception:
                pass
            return f"{group_name} ({abbreviation})"

        error_text = _extract_page_error(resp2.text)
        raise Exception(error_text or f"Step {step_val} failed")

    error_text = _extract_page_error(resp.text)
    raise Exception(error_text or "Group creation failed")


# ---------------------------------------------------------------------------
# Internal: join group
# ---------------------------------------------------------------------------

def _join_one_group(session, group_name, group_url, _log):
    """
    Join a single group. Returns "ok" on success, "already_member" if already joined.
    Raises Exception on failure.
    """
    # GET the group page — use the FINAL url (handles /groups/name -> /groups/name/ redirects)
    page_resp = session.session.get(group_url, timeout=15)
    if page_resp.status_code != 200:
        raise Exception(f"Cannot access group page: HTTP {page_resp.status_code}")

    canonical_url = page_resp.url  # This is the real URL after redirects

    # Check if page is an error
    if "<title>" in page_resp.text:
        title_m = re.search(r'<title>([^<]+)</title>', page_resp.text)
        if title_m and ("Ошибка" in title_m.group(1) or "Error" in title_m.group(1)):
            raise Exception(f"Group page is an error: {_extract_page_error(page_resp.text)}")

    # Check if already a member
    if _is_member(page_resp.text):
        return "already_member"

    # Extract session field name
    sid_field = _extract_session_field(page_resp.text) or "sessionID"

    # POST to the CANONICAL url (critical: avoids 302 redirect losing POST body)
    data = {
        sid_field: session.session_id,
        "action": "join",
    }
    headers = {
        "Referer": canonical_url,
        "Origin": session.BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }

    resp = session.session.post(canonical_url, data=data, headers=headers, timeout=15)

    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}")

    # Check response — could be JSON (AJAX) or HTML (redirect)
    try:
        result = resp.json()
        if result is True or (isinstance(result, dict) and result.get("success")):
            return "ok"
    except ValueError:
        pass

    # HTML response — check if we're now a member
    if _is_member(resp.text):
        return "ok"

    # Check for error page
    if "<title>" in resp.text:
        title_m = re.search(r'<title>([^<]+)</title>', resp.text)
        if title_m and ("Ошибка" in title_m.group(1) or "Error" in title_m.group(1)):
            error_text = _extract_page_error(resp.text)
            err_lower = error_text.lower()
            # Detect invite-only / restricted groups
            if "required permissions" in err_lower or "не имеете прав" in err_lower:
                return "restricted"
            # Detect full / max pending groups
            if "maximum number of pending" in err_lower or "максимальное количество" in err_lower:
                return "full"
            # Detect broken / deleted / temporarily unavailable groups
            if "problem trying to join" in err_lower or "try again later" in err_lower:
                return "broken"
            raise Exception(error_text)

    # If the page still has a join button, it didn't work
    if "action=join" in resp.text or "JoinGroupBtn" in resp.text:
        raise Exception("Join button still present — request was ignored")

    return "ok"


def _is_member(html):
    """Check if the HTML page indicates the user is already a member."""
    indicators = [
        "action=leaveGroup",
        "LeaveGroupBtn",
        "groupLeave",
        "You are a member",
        "Вы участник",
        "Leave this group",
        "Покинуть группу",
    ]
    for indicator in indicators:
        if indicator in html:
            return True
    return False


# ---------------------------------------------------------------------------
# Internal: group pool
# ---------------------------------------------------------------------------

# Module-level cache — loaded once from group_pool.json, reused for all accounts
_group_pool_cache = []
_group_pool_loaded = False
_group_pool_lock = threading.Lock()


def _load_group_pool(_log):
    """Load pre-scraped group pool from JSON file. Thread-safe."""
    import json

    global _group_pool_cache, _group_pool_loaded

    with _group_pool_lock:
        if _group_pool_loaded and _group_pool_cache:
            _log(f"  [INFO] Using cached group pool: {len(_group_pool_cache)} groups")
            return list(_group_pool_cache)

        pool_path = os.path.join(_DATA_DIR, "group_pool.json")
        if os.path.exists(pool_path):
            try:
                with open(pool_path, encoding="utf-8") as f:
                    data = json.load(f)
                _group_pool_cache = [
                    (item["slug"], item["url"])
                    for item in data
                    if "slug" in item and "url" in item
                ]
                random.shuffle(_group_pool_cache)
                _group_pool_loaded = True
                _log(f"  [INFO] Loaded {len(_group_pool_cache)} groups from group_pool.json")
                return list(_group_pool_cache)
            except Exception as e:
                _log(f"  [WARN] Failed to load group_pool.json: {e}")

        _log(f"  [WARN] group_pool.json not found or empty — run scrape_groups.py first")
        _group_pool_loaded = True
        return []


def reset_group_pool():
    """Reset the cached group pool (call between separate runs if needed)."""
    global _group_pool_cache, _group_pool_loaded
    with _group_pool_lock:
        _group_pool_cache = []
        _group_pool_loaded = False


def _remove_from_pool(slug_lower):
    """Remove a bad group from the in-memory cache (thread-safe)."""
    with _group_pool_lock:
        _group_pool_cache[:] = [
            (s, u) for s, u in _group_pool_cache if s.lower() != slug_lower
        ]


def _get_candidate_groups(session, _log, pool_size=3000):
    """Get candidate groups from the cached pool."""
    return _load_group_pool(_log)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_session_field(html):
    """Extract the session field name (sessionid or sessionID) from HTML form."""
    m = re.search(r'name=["\']?(sessionid|sessionID)["\']?\s', html, re.I)
    if m:
        return m.group(1)
    return None


def _extract_page_error(html):
    """Extract human-readable error text from a Steam error page."""
    # Method 1: Look for Steam's error content div pattern
    # Steam error pages: <h2>Ошибка/Error</h2> ... <h3>Извините!/Sorry!</h3> ... <p>text</p>
    for pattern in [
        r'Извините!\s*</h3>\s*(.+?)\s*<',
        r'Sorry!\s*</h3>\s*(.+?)\s*<',
        r'произошла ошибка:\s*</?\w[^>]*>\s*(.+?)\s*<',
        r'error occurred:\s*</?\w[^>]*>\s*(.+?)\s*<',
        r'class="[^"]*error_msg[^"]*"[^>]*>([^<]+)',
        r'class="[^"]*formRowFields[^"]*"[^>]*>([^<]+)',
        r'<div[^>]*style="[^"]*color:\s*red[^"]*"[^>]*>([^<]+)',
        r'class="[^"]*rgError[^"]*"[^>]*>([^<]+)',
    ]:
        m = re.search(pattern, html, re.I | re.DOTALL)
        if m:
            text = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            if len(text) > 5:
                return text

    # Method 2: Find text between "Sorry"/"Извините" and the next major element
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', '\n', clean)
    lines = [l.strip() for l in clean.split('\n') if l.strip()]

    # Find "Sorry"/"Извините" and take the next few lines
    for i, line in enumerate(lines):
        if "Извините" in line or "Sorry" in line:
            error_lines = []
            for j in range(i + 1, min(i + 5, len(lines))):
                l = lines[j].strip()
                if len(l) > 5 and l not in ("&nbsp;", ):
                    error_lines.append(l)
            if error_lines:
                return ' '.join(error_lines)

    return "Unknown Steam error"


def _upload_group_avatar(session, group_url):
    """Upload random avatar to a created group."""
    avatar_bytes = generate_random_avatar(184)

    resp = session.get(group_url)
    gid_match = re.search(r'"groupId"\s*:\s*"(\d+)"', resp.text)
    if not gid_match:
        gid_match = re.search(r'gId\s*=\s*"(\d+)"', resp.text)
    if not gid_match:
        return

    gid = gid_match.group(1)
    files = {"avatar": ("avatar.png", avatar_bytes, "image/png")}
    data = {
        "type": "group_avatar_image",
        "sId": gid,
        "sessionid": session.session_id,
        "doSub": "1",
        "json": "1",
    }
    headers = {"Referer": group_url, "Origin": session.BASE_URL}
    session.session.post(
        f"{session.BASE_URL}/actions/FileUploader",
        data=data, files=files, headers=headers, timeout=15,
    )
