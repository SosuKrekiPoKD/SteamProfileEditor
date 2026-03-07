import json
import hmac
import hashlib
import struct
import time
import base64
import os
from typing import Optional

STEAM_CHARS = "23456789BCDFGHJKMNPQRTVWXY"


def generate_steam_guard_code(shared_secret: str) -> str:
    timestamp = int(time.time())
    time_counter = timestamp // 30
    secret = base64.b64decode(shared_secret)
    msg = struct.pack(">Q", time_counter)
    hmac_hash = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = hmac_hash[-1] & 0x0F
    code_int = struct.unpack(">I", hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF
    code = ""
    for _ in range(5):
        code += STEAM_CHARS[code_int % len(STEAM_CHARS)]
        code_int //= len(STEAM_CHARS)
    return code


def load_mafile(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_2fa_code_from_mafile(mafile_data: dict) -> Optional[str]:
    shared_secret = mafile_data.get("shared_secret")
    if not shared_secret:
        return None
    return generate_steam_guard_code(shared_secret)
