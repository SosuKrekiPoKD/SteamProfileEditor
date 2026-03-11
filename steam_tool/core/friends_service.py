import random
import re
import time
from typing import Optional

from core.steam_auth import SteamSession, SteamAuthError
from core.account_manager import Account
from core.proxy_manager import ProxyManager


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
        log_callback(f"=== Phase 1: Logging in {len(all_unique)} accounts ===")

    sessions = {}       # username -> SteamSession
    real_steam_ids = {}  # username -> SteamID64

    for acc in all_unique:
        if cancel_event and cancel_event.is_set():
            return

        proxy = None
        if use_proxies and proxy_manager:
            proxy = proxy_manager.acquire()

        try:
            session = SteamSession(
                username=acc.username,
                password=acc.password,
                mafile_data=acc.mafile_data if acc.has_mafile else None,
                proxy=proxy,
                log_callback=log_callback,
            )
            session.login()
            sessions[acc.username] = session
            real_steam_ids[acc.username] = session.steam_id
            if log_callback:
                log_callback(f"[OK] {acc.username} logged in (SteamID64: {session.steam_id})")
        except SteamAuthError as e:
            if log_callback:
                log_callback(f"[FAIL] Login failed for {acc.username}: {_diagnose_error(str(e))}")

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
                     f"{len(logged_pool)} in pool) ===")

    # ===== PHASE 2: Add friends =====
    total_pairs = 0
    completed_pairs = 0

    for acc in logged_selected:
        if cancel_event and cancel_event.is_set():
            break

        session = sessions[acc.username]
        # Pool candidates = all logged-in accounts except self
        pool = [a for a in logged_pool if a.username != acc.username]
        if not pool:
            continue

        friend_count = random.randint(min_friends, min(max_friends, len(pool)))

        if log_callback:
            log_callback(f"--- {acc.username}: adding {friend_count} friends ---")

        # Get current friend list
        our_steam_ids = list(real_steam_ids.values())
        current_friends = _get_friends_from_list(session, our_steam_ids)

        # Pick random targets from pool
        targets = random.sample(pool, min(friend_count, len(pool)))

        # Replace already-friended targets
        final_targets = []
        used_names = {t.username for t in targets}
        used_names.add(acc.username)

        for t in targets:
            target_sid = real_steam_ids.get(t.username, "")
            if target_sid and target_sid in current_friends:
                # Find replacement
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

        total_pairs += len(final_targets)

        for target in final_targets:
            if cancel_event and cancel_event.is_set():
                break

            target_sid = real_steam_ids.get(target.username, "")
            if not target_sid:
                if log_callback:
                    log_callback(f"[FAIL] {target.username}: no SteamID64")
                completed_pairs += 1
                if progress_callback:
                    progress_callback(completed_pairs, total_pairs)
                continue

            # Send friend request
            success, err = _send_friend_request(session, target_sid, log_callback)
            if success:
                if log_callback:
                    log_callback(f"[OK] {acc.username} -> sent request to {target.username}")

                # Accept from target side
                target_session = sessions.get(target.username)
                if target_session:
                    my_sid = real_steam_ids[acc.username]
                    accepted, acc_err = _accept_friend_request(target_session, my_sid, log_callback)
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
                if log_callback:
                    log_callback(
                        f"[FAIL] {acc.username} -> failed to add "
                        f"{target.username}: {_diagnose_error(err)}"
                    )

            completed_pairs += 1
            if progress_callback:
                progress_callback(completed_pairs, total_pairs)

            time.sleep(random.uniform(1.0, 3.0))

    if log_callback:
        log_callback(f"Friend adding complete. {completed_pairs}/{total_pairs} pairs processed.")


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
