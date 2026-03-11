import requests
import time
import base64
from typing import Optional

from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import PKCS1_v1_5

from core.steam_guard import generate_steam_guard_code


class SteamAuthError(Exception):
    pass


class SteamSession:
    """Manages a Steam web session with authentication."""

    BASE_URL = "https://steamcommunity.com"
    API_URL = "https://api.steampowered.com"

    def __init__(self, username: str, password: str, mafile_data: Optional[dict] = None,
                 proxy: Optional[dict] = None, log_callback=None):
        self.username = username
        self.password = password
        self.mafile_data = mafile_data
        self.steam_id = None
        self.session_id = None
        self.access_token = None
        self.log_callback = log_callback
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })
        if proxy:
            self.session.proxies.update(proxy)
        self.logged_in = False

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def login(self) -> bool:
        try:
            # Step 1: Get RSA key
            self._log(f"[{self.username}] Getting RSA key...")
            rsa_data = self._get_rsa_key()

            # Step 2: Encrypt password
            encrypted_password = self._encrypt_password(
                rsa_data["publickey_mod"],
                rsa_data["publickey_exp"],
            )
            self._log(f"[{self.username}] Password encrypted")

            # Step 3: Get 2FA code if mafile available
            twofactor_code = ""
            if self.mafile_data:
                shared_secret = self.mafile_data.get("shared_secret", "")
                if shared_secret:
                    twofactor_code = generate_steam_guard_code(shared_secret)
                    self._log(f"[{self.username}] 2FA code generated: {twofactor_code}")

            # Step 4: Begin auth session
            self._log(f"[{self.username}] Starting auth session...")
            self._begin_auth_session(encrypted_password, rsa_data["timestamp"],
                                     twofactor_code)
            return self.logged_in

        except SteamAuthError:
            raise
        except Exception as e:
            raise SteamAuthError(f"Login failed for {self.username}: {e}")

    def _get_rsa_key(self) -> dict:
        url = f"{self.API_URL}/IAuthenticationService/GetPasswordRSAPublicKey/v1/"
        try:
            resp = self.session.get(url, params={"account_name": self.username}, timeout=15)
        except requests.RequestException as e:
            raise SteamAuthError(f"Cannot reach Steam API: {e}")
        if resp.status_code != 200:
            raise SteamAuthError(f"RSA key request failed: HTTP {resp.status_code}")
        data = resp.json().get("response", {})
        if not data.get("publickey_mod"):
            raise SteamAuthError("Empty RSA key (wrong username?)")
        return data

    def _encrypt_password(self, mod_hex: str, exp_hex: str) -> str:
        mod = int(mod_hex, 16)
        exp = int(exp_hex, 16)
        rsa_key = RSA.construct((mod, exp))
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted = cipher.encrypt(self.password.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def _begin_auth_session(self, encrypted_password: str, timestamp: str,
                            twofactor_code: str):
        url = f"{self.API_URL}/IAuthenticationService/BeginAuthSessionViaCredentials/v1/"
        data = {
            "account_name": self.username,
            "encrypted_password": encrypted_password,
            "encryption_timestamp": timestamp,
            "persistence": 1,
            "website_id": "Community",
        }
        try:
            resp = self.session.post(url, data=data, timeout=15)
        except requests.RequestException as e:
            raise SteamAuthError(f"Auth request failed: {e}")

        if resp.status_code != 200:
            raise SteamAuthError(f"BeginAuthSession HTTP {resp.status_code}")

        result = resp.json().get("response", {})
        client_id = result.get("client_id")
        request_id = result.get("request_id")
        steamid = result.get("steamid")
        allowed = result.get("allowed_confirmations", [])

        self._log(f"[{self.username}] Auth response: client_id={client_id}, "
                  f"steamid={steamid}, confirmations={allowed}")

        if not client_id:
            error_msg = result.get("extended_error_message", "")
            raise SteamAuthError(
                f"Auth rejected. {error_msg or 'Wrong password or account locked?'}"
            )

        self.steam_id = str(steamid)

        # Determine what confirmation type Steam wants
        guard_type = None
        for conf in allowed:
            ct = conf.get("confirmation_type")
            if ct is not None:
                guard_type = ct
                break

        self._log(f"[{self.username}] Guard type required: {guard_type}")

        # Submit 2FA code if needed
        # guard_type 3 = DeviceCode (Steam Guard TOTP)
        # guard_type 2 = EmailCode
        if twofactor_code and guard_type in (3, None):
            self._log(f"[{self.username}] Submitting 2FA code (type=3 DeviceCode)...")
            self._submit_steam_guard_code(client_id, steamid, twofactor_code, code_type=3)
        elif twofactor_code and guard_type == 2:
            self._log(f"[{self.username}] Steam wants email code, trying TOTP anyway...")
            self._submit_steam_guard_code(client_id, steamid, twofactor_code, code_type=3)

        # Poll for auth status
        self._log(f"[{self.username}] Polling for auth confirmation...")
        self._poll_auth_status(client_id, request_id)

    def _submit_steam_guard_code(self, client_id, steamid, code: str, code_type: int = 3):
        url = f"{self.API_URL}/IAuthenticationService/UpdateAuthSessionWithSteamGuardCode/v1/"
        data = {
            "client_id": str(client_id),
            "steamid": str(steamid),
            "code": code,
            "code_type": code_type,
        }
        try:
            resp = self.session.post(url, data=data, timeout=15)
        except requests.RequestException as e:
            raise SteamAuthError(f"2FA submit network error: {e}")

        self._log(f"[{self.username}] 2FA response: HTTP {resp.status_code}")

        if resp.status_code != 200:
            try:
                err_body = resp.json()
            except ValueError:
                err_body = resp.text[:200]
            raise SteamAuthError(f"2FA rejected: HTTP {resp.status_code}, body: {err_body}")

    def _poll_auth_status(self, client_id, request_id):
        url = f"{self.API_URL}/IAuthenticationService/PollAuthSessionStatus/v1/"
        for attempt in range(15):
            try:
                resp = self.session.post(url, data={
                    "client_id": str(client_id),
                    "request_id": str(request_id),
                }, timeout=15)
            except requests.RequestException as e:
                self._log(f"[{self.username}] Poll attempt {attempt+1} failed: {e}")
                time.sleep(2)
                continue

            if resp.status_code != 200:
                self._log(f"[{self.username}] Poll HTTP {resp.status_code}, retrying...")
                time.sleep(2)
                continue

            result = resp.json().get("response", {})
            refresh_token = result.get("refresh_token")
            access_token = result.get("access_token")

            self._log(f"[{self.username}] Poll attempt {attempt+1}: "
                      f"has_refresh={bool(refresh_token)}, has_access={bool(access_token)}")

            if refresh_token and access_token:
                self._log(f"[{self.username}] Got tokens, finalizing login...")
                self._finalize_login(refresh_token, access_token)
                return
            time.sleep(2)

        raise SteamAuthError("Auth polling timed out (Steam didn't confirm login)")

    def _finalize_login(self, refresh_token: str, access_token: str):
        self.access_token = access_token

        # Get initial sessionid cookie
        session_id = self._get_session_id()

        # JWT FinalizeLogin — sets proper steamLoginSecure cookies via transfers
        try:
            resp = self.session.post(
                "https://login.steampowered.com/jwt/finalizelogin",
                data={
                    "nonce": refresh_token,
                    "sessionid": session_id,
                    "redir": "https://steamcommunity.com/login/home/?goto=",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            finalize_data = resp.json()
            transfer_info = finalize_data.get("transfer_info", [])
            self._log(f"[{self.username}] FinalizeLogin: {len(transfer_info)} transfers")

            for ti in transfer_info:
                params = dict(ti["params"])
                params["steamID"] = finalize_data["steamID"]
                self.session.post(ti["url"], data=params, timeout=15)

        except Exception as e:
            self._log(f"[{self.username}] FinalizeLogin failed: {e}")
            raise SteamAuthError(f"FinalizeLogin failed: {e}")

        # Read sessionid from cookies (may have been updated by transfers)
        for c in self.session.cookies:
            if c.name == "sessionid" and "steamcommunity" in (c.domain or ""):
                session_id = c.value
                break

        has_secure = any(c.name == "steamLoginSecure" for c in self.session.cookies)
        self._log(f"[{self.username}] steamLoginSecure set: {has_secure}")

        self.session_id = session_id
        self.logged_in = True
        self._log(f"[OK] {self.username} logged in (SteamID: {self.steam_id}, "
                  f"sessionid: {self.session_id[:8] if self.session_id else 'EMPTY'}...)")

    def _get_session_id(self) -> str:
        # Try multiple ways to get session_id from cookies
        cookies = self.session.cookies
        session_id = None
        # Try with specific domain
        for domain in ["steamcommunity.com", ".steamcommunity.com"]:
            session_id = cookies.get("sessionid", domain=domain)
            if session_id:
                break
        # Try without domain filter
        if not session_id:
            for cookie in cookies:
                if cookie.name == "sessionid":
                    session_id = cookie.value
                    break
        # Visit Steam Community to get cookie
        if not session_id:
            try:
                self.session.get(self.BASE_URL, timeout=10)
            except requests.RequestException:
                pass
            for cookie in cookies:
                if cookie.name == "sessionid":
                    session_id = cookie.value
                    break
        # Last resort: generate a random session_id (24 hex chars)
        if not session_id:
            import secrets
            session_id = secrets.token_hex(12)
            self._log(f"[{self.username}] Generated random sessionid")
        return session_id

    def get(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", 15)
        return self.session.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", 15)
        return self.session.post(url, **kwargs)

    @property
    def profile_url(self) -> str:
        return f"{self.BASE_URL}/profiles/{self.steam_id}"
