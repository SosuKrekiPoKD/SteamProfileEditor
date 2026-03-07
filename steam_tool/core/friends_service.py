import random
import re
import time
from typing import Optional

from core.steam_auth import SteamSession, SteamAuthError
from core.account_manager import Account
from core.proxy_manager import ProxyManager


def add_friends_between_accounts(
    accounts: list,
    min_friends: int,
    max_friends: int,
    proxy_manager: Optional[ProxyManager] = None,
    use_proxies: bool = False,
    log_callback=None,
    progress_callback=None,
    cancel_event=None,
):
    """
    Add friends between loaded accounts.

    Phase 1: Login ALL accounts first to get correct SteamID64s.
    Phase 2: For each account, pick random friends and add them.
    """
    if len(accounts) < 2:
        if log_callback:
            log_callback("[ERROR] Need at least 2 accounts for friend adding")
        return

    total_accounts = len(accounts)

    # ===== PHASE 1: Login all accounts to get real SteamID64 =====
    if log_callback:
        log_callback(f"=== Phase 1: Logging in {total_accounts} accounts ===")

    sessions = {}
    real_steam_ids = {}  # index -> SteamID64

    for idx in range(total_accounts):
        if cancel_event and cancel_event.is_set():
            return

        acc = accounts[idx]
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
            sessions[idx] = session
            real_steam_ids[idx] = session.steam_id
            if log_callback:
                log_callback(f"[OK] {acc.username} logged in (SteamID64: {session.steam_id})")
        except SteamAuthError as e:
            if log_callback:
                log_callback(f"[FAIL] Login failed for {acc.username}: {_diagnose_error(str(e))}")

    logged_in_indices = list(sessions.keys())
    if len(logged_in_indices) < 2:
        if log_callback:
            log_callback("[ERROR] Less than 2 accounts logged in, cannot add friends")
        return

    if log_callback:
        log_callback(f"=== Phase 2: Adding friends ({len(logged_in_indices)} accounts online) ===")

    # ===== PHASE 2: Add friends =====
    total_pairs = 0
    completed_pairs = 0

    for i in logged_in_indices:
        if cancel_event and cancel_event.is_set():
            break

        acc = accounts[i]
        session = sessions[i]
        friend_count = random.randint(min_friends, min(max_friends, len(logged_in_indices) - 1))

        if log_callback:
            log_callback(f"--- {acc.username}: adding {friend_count} friends ---")

        # Get current friend list (only our accounts' SteamID64s)
        our_steam_ids = list(real_steam_ids.values())
        current_friends = _get_friends_from_list(session, our_steam_ids)

        # Pick random targets (excluding self, only from logged-in accounts)
        candidates = [j for j in logged_in_indices if j != i]
        targets = random.sample(candidates, min(friend_count, len(candidates)))

        # Replace already-friended targets
        final_targets = []
        used_indices = set(targets)
        used_indices.add(i)

        for t in targets:
            target_sid = real_steam_ids.get(t, "")
            if target_sid and target_sid in current_friends:
                replacement = _find_replacement(candidates, used_indices)
                if replacement is not None:
                    used_indices.add(replacement)
                    repl_sid = real_steam_ids.get(replacement, "")
                    if repl_sid and repl_sid in current_friends:
                        if log_callback:
                            log_callback(
                                f"[WARN] {acc.username}: {accounts[t].username} already friend, "
                                f"replacement also friend — skipping"
                            )
                        continue
                    final_targets.append(replacement)
                    if log_callback:
                        log_callback(
                            f"[INFO] {acc.username}: {accounts[t].username} already friend, "
                            f"replaced with {accounts[replacement].username}"
                        )
            else:
                final_targets.append(t)

        total_pairs += len(final_targets)

        for t_idx in final_targets:
            if cancel_event and cancel_event.is_set():
                break

            target = accounts[t_idx]
            target_sid = real_steam_ids.get(t_idx, "")

            if not target_sid:
                if log_callback:
                    log_callback(f"[FAIL] {target.username}: no SteamID64")
                completed_pairs += 1
                if progress_callback:
                    progress_callback(completed_pairs, total_pairs)
                continue

            # Send friend request using real SteamID64
            success, err = _send_friend_request(session, target_sid, log_callback)
            if success:
                if log_callback:
                    log_callback(f"[OK] {acc.username} -> sent request to {target.username}")

                # Accept from target side
                target_session = sessions.get(t_idx)
                if target_session:
                    my_sid = real_steam_ids[i]
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
