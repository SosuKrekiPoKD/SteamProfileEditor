import os
import random
import re
import time

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

    for group_name, group_url in candidates:
        if len(joined) >= count:
            break

        normalized = group_name.lower()
        if normalized in used_groups:
            _log(f"  [SKIP] {group_name}: already used by another account")
            continue

        try:
            result = _join_one_group(session, group_name, group_url, _log)
            if result == "already_member":
                _log(f"  [SKIP] {group_name}: already a member")
                used_groups.add(normalized)
                continue
            joined.append(group_name)
            used_groups.add(normalized)
            _log(f"[OK] {account.username}: Joined group #{len(joined)}: {group_name}")
        except Exception as e:
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

    _log(f"  [DEBUG] POST join to: {canonical_url}")
    resp = session.session.post(canonical_url, data=data, headers=headers, timeout=15)
    _log(f"  [DEBUG] Response: HTTP {resp.status_code}, body[:200]={resp.text[:200]}")

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
            raise Exception(_extract_page_error(resp.text))

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

# Module-level cache — built once, reused for all accounts in a session
_group_pool_cache = []
_group_pool_built = False

def _load_search_terms():
    path = os.path.join(_DATA_DIR, "search_terms.txt")
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _build_group_pool(session, _log, target_size=3000):
    """
    Build a massive group pool using paginated Steam search.
    Called once, result is cached for all subsequent accounts.
    """
    global _group_pool_cache, _group_pool_built

    if _group_pool_built and len(_group_pool_cache) > 0:
        _log(f"  [INFO] Using cached group pool: {len(_group_pool_cache)} groups")
        return list(_group_pool_cache)

    _log(f"  [INFO] Building group pool (target: {target_size})...")
    candidates = []
    seen = set()

    search_url = f"{session.BASE_URL}/search/groups/"
    terms = _load_search_terms()
    random.shuffle(terms)

    for term in terms:
        if len(candidates) >= target_size:
            break

        # Paginate: each page has ~20 groups, fetch up to 5 pages per term
        for page in range(1, 6):
            if len(candidates) >= target_size:
                break
            try:
                resp = session.get(
                    search_url,
                    params={"text": term, "filter": "none", "page": page},
                )
                if resp.status_code != 200:
                    break

                found = re.findall(
                    r'href="(https://steamcommunity\.com/groups/([^"]+))"',
                    resp.text,
                )
                if not found:
                    break  # No more results for this term

                new_count = 0
                for url, name in found:
                    key = name.lower().rstrip("/")
                    if key not in seen:
                        seen.add(key)
                        candidates.append((name.rstrip("/"), url))
                        new_count += 1

                if new_count == 0:
                    break  # All groups on this page were duplicates

                # Small delay to avoid rate limiting
                time.sleep(0.3)

            except Exception:
                break

    _group_pool_cache = candidates
    _group_pool_built = True
    _log(f"  [INFO] Group pool built: {len(candidates)} unique groups")
    return list(candidates)


def reset_group_pool():
    """Reset the cached group pool (call between separate runs if needed)."""
    global _group_pool_cache, _group_pool_built
    _group_pool_cache = []
    _group_pool_built = False


def _get_candidate_groups(session, _log, pool_size=3000):
    """Get candidate groups from the cached pool."""
    return _build_group_pool(session, _log, target_size=pool_size)


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
