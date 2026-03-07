import os
import json
import glob
from dataclasses import dataclass, field


@dataclass
class Account:
    username: str
    password: str
    steam_id: str = ""
    mafile_data: dict = field(default_factory=dict)
    has_mafile: bool = False

    @property
    def display_name(self) -> str:
        return self.username

    @property
    def shared_secret(self) -> str:
        return self.mafile_data.get("shared_secret", "")

    @property
    def identity_secret(self) -> str:
        return self.mafile_data.get("identity_secret", "")


class AccountManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.accounts_file = os.path.join(data_dir, "accounts.txt")
        self.mafiles_dir = os.path.join(data_dir, "mafiles")
        self.accounts: list[Account] = []

    def load(self) -> list[Account]:
        self.accounts.clear()
        credentials = self._load_credentials()
        mafiles = self._load_mafiles()

        # Match accounts with mafiles by account_name
        mafile_by_name: dict[str, dict] = {}
        for mf in mafiles:
            name = mf.get("account_name", "").lower()
            if name:
                mafile_by_name[name] = mf

        for username, password in credentials:
            mf_data = mafile_by_name.get(username.lower(), {})
            steam_id = str(mf_data.get("Session", {}).get("SteamID", ""))
            if not steam_id:
                steam_id = str(mf_data.get("steam_id", ""))

            account = Account(
                username=username,
                password=password,
                steam_id=steam_id,
                mafile_data=mf_data,
                has_mafile=bool(mf_data),
            )
            self.accounts.append(account)

        return self.accounts

    def _load_credentials(self) -> list[tuple[str, str]]:
        if not os.path.exists(self.accounts_file):
            return []
        credentials = []
        with open(self.accounts_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                parts = line.split(":", 1)
                if len(parts) == 2:
                    credentials.append((parts[0].strip(), parts[1].strip()))
        return credentials

    def _load_mafiles(self) -> list[dict]:
        if not os.path.isdir(self.mafiles_dir):
            os.makedirs(self.mafiles_dir, exist_ok=True)
            return []
        mafiles = []
        for path in glob.glob(os.path.join(self.mafiles_dir, "*.maFile")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                mafiles.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        # Also try lowercase extension
        for path in glob.glob(os.path.join(self.mafiles_dir, "*.mafile")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if data not in mafiles:
                    mafiles.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return mafiles

    @property
    def count(self) -> int:
        return len(self.accounts)

    def get_steam_ids(self) -> list[str]:
        return [a.steam_id for a in self.accounts if a.steam_id]
