import random
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from core.steam_auth import SteamSession, SteamAuthError
from core.account_manager import Account
from core.proxy_manager import ProxyManager

MAX_PROXY_RETRIES = 3


def add_friends_between_accounts(
    selected_accounts: list,
    all_accounts: list,
    min_friends: int,
    max_friends: int,
    proxy_manager: Optional[ProxyManager] = None,
    use_proxies: bool = False,
    log_callback=None,
    progress_callback=None,
    cancel_event=None,
    threads: int = 1,
):
    """
    Add friends to selected accounts from the full account pool.

    selected_accounts: accounts that RECEIVE friends
    all_accounts: full pool of accounts that can become friends (includes selected)

    Phase 1: Login all unique accounts (selected + potential friends).
    Phase 2: For each selected account, pick random friends from the pool.
    """
    if len(selected_accounts) < 1:
        if log_callback:
            log_callback("[ERROR] Need at least 1 selected account")
        return
    if len(all_accounts) < 2:
        if log_callback:
            log_callback("[ERROR] Need at least 2 accounts in total for friend adding")
        return

    # Build unique list of all accounts to login (selected + pool)
    all_unique = []
    seen_usernames = set()
    for acc in list(selected_accounts) + list(all_accounts):
        if acc.username not in seen_usernames:
            seen_usernames.add(acc.username)
            all_unique.append(acc)

    selected_usernames = {a.username for a in selected_accounts}

    # ===== PHASE 1: Login all accounts to get real SteamID64 =====
    if log_callback:
        log_callback(f"=== Phase 1: Logging in {len(all_unique)} accounts ({threads} threads) ===")

    sessions = {}       # username -> SteamSession
    real_steam_ids = {}  # username -> SteamID64
    _login_lock = threading.Lock()

    def _login_one(acc):
        if cancel_event and cancel_event.is_set():
            return

        proxy = None
        if use_proxies and proxy_manager:
            proxy = proxy_manager.acquire()

        retries = MAX_PROXY_RETRIES if (use_proxies and proxy_manager) else 1
        last_error = ""

        for attempt in range(retries):
            if cancel_event and cancel_event.is_set():
                return
            try:
                session = SteamSession(
                    username=acc.username,
                    password=acc.password,
                    mafile_data=acc.mafile_data if acc.has_mafile else None,
                    proxy=proxy,
                    log_callback=log_callback,
                )
                session.login()
                with _login_lock:
                    sessions[acc.username] = session
                    real_steam_ids[acc.username] = session.steam_id
                if log_callback:
                    log_callback(f"[OK] {acc.username} logged in (SteamID64: {session.steam_id})")
                return
            except (SteamAuthError, Exception) as e:
                last_error = str(e)
                if attempt < retries - 1 and use_proxies and proxy_manager:
                    if log_callback:
                        log_callback(
                            f"[RETRY] {acc.username}: login failed ({_diagnose_error(last_error)}), "
                            f"switching proxy (attempt {attempt + 1}/{retries})..."
                        )
                    proxy = proxy_manager.get_different(proxy)
                    if proxy is None:
                        if log_callback:
                            log_callback(f"[FAIL] {acc.username}: no more proxies available")
                        return

        if log_callback:
            log_callback(f"[FAIL] Login failed for {acc.username}: {_diagnose_error(last_error)}")

    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(_login_one, acc) for acc in all_unique]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
    else:
        for acc in all_unique:
            if cancel_event and cancel_event.is_set():
                return
            _login_one(acc)

    # Check we have enough logged-in accounts
    logged_selected = [a for a in selected_accounts if a.username in sessions]
    logged_pool = [a for a in all_unique if a.username in sessions]

    if not logged_selected:
        if log_callback:
            log_callback("[ERROR] No selected accounts logged in")
        return
    if len(logged_pool) < 2:
        if log_callback:
            log_callback("[ERROR] Less than 2 accounts logged in, cannot add friends")
        return

    if log_callback:
        log_callback(f"=== Phase 2: Adding friends ({len(logged_selected)} selected, "
                     f"{len(logged_pool)} in pool, {threads} threads) ===")

    # ===== PHASE 2: Add friends =====
    _progress_lock = threading.Lock()
    _counters = {"total": 0, "completed": 0}

    def _rotate_proxy(sess):
        """Switch session to a different proxy. Returns True if rotated."""
        if not use_proxies or not proxy_manager:
            return False
        old = sess.session.proxies.get("https", "")
        new_proxy = proxy_manager.get_different({"https": old, "http": old} if old else None)
        if new_proxy:
            sess.session.proxies.update(new_proxy)
            return True
        return False

    def _process_one_account(acc):
        if cancel_event and cancel_event.is_set():
            return

        session = sessions[acc.username]
        consecutive_proxy_fails = 0

        pool = [a for a in logged_pool if a.username != acc.username]
        if not pool:
            return

        friend_count = random.randint(min_friends, min(max_friends, len(pool)))

        if log_callback:
            log_callback(f"--- {acc.username}: adding {friend_count} friends ---")

        our_steam_ids = list(real_steam_ids.values())
        current_friends = _get_friends_from_list(session, our_steam_ids)

        targets = random.sample(pool, min(friend_count, len(pool)))

        final_targets = []
        used_names = {t.username for t in targets}
        used_names.add(acc.username)

        for t in targets:
            target_sid = real_steam_ids.get(t.username, "")
            if target_sid and target_sid in current_friends:
                available = [a for a in pool if a.username not in used_names]
                if available:
                    repl = random.choice(available)
                    used_names.add(repl.username)
                    repl_sid = real_steam_ids.get(repl.username, "")
                    if repl_sid and repl_sid in current_friends:
                        if log_callback:
                            log_callback(
                                f"[WARN] {acc.username}: {t.username} already friend, "
                                f"replacement also friend — skipping"
                            )
                        continue
                    final_targets.append(repl)
                    if log_callback:
                        log_callback(
                            f"[INFO] {acc.username}: {t.username} already friend, "
                            f"replaced with {repl.username}"
                        )
                else:
                    if log_callback:
                        log_callback(f"[WARN] {acc.username}: {t.username} already friend, no replacement")
            else:
                final_targets.append(t)

        with _progress_lock:
            _counters["total"] += len(final_targets)

        for target in final_targets:
            if cancel_event and cancel_event.is_set():
                break

            target_sid = real_steam_ids.get(target.username, "")
            if not target_sid:
                if log_callback:
                    log_callback(f"[FAIL] {target.username}: no SteamID64")
                with _progress_lock:
                    _counters["completed"] += 1
                    if progress_callback:
                        progress_callback(_counters["completed"], _counters["total"])
                continue

            # Send friend request with proxy retry
            success, err = False, ""
            for attempt in range(MAX_PROXY_RETRIES):
                success, err = _send_friend_request(session, target_sid, log_callback)
                if success or not _is_proxy_error(err):
                    break
                if attempt < MAX_PROXY_RETRIES - 1:
                    if _rotate_proxy(session):
                        if log_callback:
                            log_callback(
                                f"[RETRY] {acc.username}: proxy error, switched proxy "
                                f"(attempt {attempt + 1}/{MAX_PROXY_RETRIES})"
                            )
                    else:
                        break

            if success:
                consecutive_proxy_fails = 0
                if log_callback:
                    log_callback(f"[OK] {acc.username} -> sent request to {target.username}")

                # Accept from target side (also with proxy retry)
                target_session = sessions.get(target.username)
                if target_session:
                    my_sid = real_steam_ids[acc.username]
                    accepted, acc_err = False, ""
                    for attempt in range(MAX_PROXY_RETRIES):
                        accepted, acc_err = _accept_friend_request(target_session, my_sid, log_callback)
                        if accepted or not _is_proxy_error(acc_err):
                            break
                        if attempt < MAX_PROXY_RETRIES - 1:
                            if _rotate_proxy(target_session):
                                if log_callback:
                                    log_callback(
                                        f"[RETRY] {target.username}: proxy error on accept, switched proxy "
                                        f"(attempt {attempt + 1}/{MAX_PROXY_RETRIES})"
                                    )
                            else:
                                break

                    if accepted:
                        if log_callback:
                            log_callback(f"[OK] {target.username} accepted {acc.username}")
                    else:
                        if log_callback:
                            log_callback(
                                f"[FAIL] {target.username} failed to accept "
                                f"{acc.username}: {_diagnose_error(acc_err)}"
                            )
            else:
                if _is_proxy_error(err):
                    consecutive_proxy_fails += 1
                else:
                    consecutive_proxy_fails = 0
                if log_callback:
                    log_callback(
                        f"[FAIL] {acc.username} -> failed to add "
                        f"{target.username}: {_diagnose_error(err)}"
                    )

            with _progress_lock:
                _counters["completed"] += 1
                if progress_callback:
                    progress_callback(_counters["completed"], _counters["total"])

            time.sleep(random.uniform(1.0, 3.0))

    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(_process_one_account, acc) for acc in logged_selected]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
    else:
        for acc in logged_selected:
            if cancel_event and cancel_event.is_set():
                break
            _process_one_account(acc)

    if log_callback:
        log_callback(f"Friend adding complete. {_counters['completed']}/{_counters['total']} pairs processed.")


def _is_proxy_error(error_str: str) -> bool:
    """Check if error is proxy/network related (worth retrying with different proxy)."""
    err = error_str.lower()
    return any(kw in err for kw in (
        "proxy", "proxyerror", "tunnel", "timed out", "timeout",
        "connection refused", "connectionerror", "no exit node",
        "max retries exceeded",
    ))


def _find_replacement(candidates, used_indices):
    available = [c for c in candidates if c not in used_indices]
    if not available:
        return None
    return random.choice(available)


def _get_friends_from_list(session, steam_ids_to_check):
    friends = set()
    try:
        url = f"{session.profile_url}/friends/"
        resp = session.get(url)
        if resp.status_code == 200:
            found_ids = re.findall(r'data-steamid="(\d+)"', resp.text)
            check_set = set(steam_ids_to_check)
            for fid in found_ids:
                if fid in check_set:
                    friends.add(fid)
    except Exception:
        pass
    return friends


def _send_friend_request(session, target_steam_id, log_callback=None):
    """Send friend invite via Steam Community."""
    url = f"{session.BASE_URL}/actions/AddFriendAjax"
    data = {
        "sessionID": session.session_id,
        "steamid": target_steam_id,
        "accept_invite": "0",
    }
    headers = {
        "Referer": f"{session.BASE_URL}/profiles/{target_steam_id}",
        "Origin": session.BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    if log_callback:
        # Log cookies being sent for debugging
        sc = session.session.cookies
        has_login = any(c.name == "steamLoginSecure" for c in sc)
        has_sid = any(c.name == "sessionid" for c in sc)
        log_callback(f"  [DEBUG] AddFriend: target={target_steam_id}, hasLoginCookie={has_login}, hasSessionid={has_sid}")
    try:
        resp = session.session.post(url, data=data, headers=headers, timeout=15)
        if log_callback:
            sent_cookies = resp.request.headers.get("Cookie", "NONE")[:200]
            sent_body = resp.request.body or "EMPTY"
            log_callback(f"  [DEBUG] Sent cookies: {sent_cookies}")
            log_callback(f"  [DEBUG] Sent body: {sent_body}")
            log_callback(f"  [DEBUG] Response: HTTP {resp.status_code}, body={resp.text[:150]}")
        if resp.status_code == 200:
            try:
                result = resp.json()
            except ValueError:
                return False, f"Non-JSON response: {resp.text[:100]}"
            if result.get("success") == 1:
                return True, ""
            return False, f"API returned success={result.get('success')}, invited={result.get('invited')}"
        body = resp.text[:200] if resp.text else "empty"
        return False, f"HTTP {resp.status_code}: {body}"
    except Exception as e:
        return False, str(e)


def _accept_friend_request(session, sender_steam_id, log_callback=None):
    """Accept a pending friend invite."""
    url = f"{session.BASE_URL}/actions/AddFriendAjax"
    data = {
        "sessionID": session.session_id,
        "steamid": sender_steam_id,
        "accept_invite": "1",
    }
    headers = {
        "Referer": f"{session.BASE_URL}/profiles/{sender_steam_id}",
        "Origin": session.BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        resp = session.session.post(url, data=data, headers=headers, timeout=15)
        if resp.status_code == 200:
            try:
                result = resp.json()
            except ValueError:
                return False, f"Non-JSON response: {resp.text[:100]}"
            # Steam returns True (bool) or {"success": 1} for accept
            if result is True or (isinstance(result, dict) and result.get("success") == 1):
                return True, ""
            if isinstance(result, dict):
                return False, f"API returned success={result.get('success')}"
            return False, f"Unexpected response: {result}"
        body = resp.text[:200] if resp.text else "empty"
        return False, f"HTTP {resp.status_code}: {body}"
    except Exception as e:
        return False, str(e)


def _diagnose_error(error_str: str) -> str:
    err = error_str.lower()
    if "proxy" in err or "proxyerror" in err or "tunnel" in err:
        return f"{error_str} [Proxy not working or blocked]"
    if "timeout" in err or "timed out" in err:
        return f"{error_str} [Connection timed out — proxy or Steam issue]"
    if "connection refused" in err or "connectionerror" in err:
        return f"{error_str} [Connection refused — check proxy/network]"
    if "429" in err or "too many" in err:
        return f"{error_str} [Rate limited — too many requests, slow down]"
    if "limited user" in err or "limited account" in err:
        return f"{error_str} [Limited account — no Steam level / not spent $5]"
    if "success=2" in err:
        return f"{error_str} [Already friends or pending invite]"
    if "success=41" in err:
        return f"{error_str} [Friend list full]"
    if "success=25" in err:
        return f"{error_str} [Limited user — cannot add friends (need Steam level 1+)]"
    if "401" in err or "unauthorized" in err:
        return f"{error_str} [Session expired — re-login needed]"
    if "400" in err:
        return f"{error_str} [Bad request — possibly invalid SteamID or limited account]"
    return error_str
