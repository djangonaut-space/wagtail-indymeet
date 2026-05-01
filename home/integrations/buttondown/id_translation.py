import uuid

# Crockford base32 omits i, l, o, u to avoid visual ambiguity
# https://www.crockford.com/base32.html
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


def _crockford_decode(s: str) -> int:
    n = 0
    for c in s.lower():
        n = n * 32 + CROCKFORD.index(c)
    return n


def _crockford_encode(n: int, length: int = 26) -> str:
    res = ""
    while n:
        res = CROCKFORD[n % 32] + res
        n //= 32
    return res.zfill(length)


def sub_to_uuid(sub_id: str) -> str:
    """Convert e.g. 'sub_5anaxvqk6cvqeyxvqzzynanexv' → 'aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb'"""
    prefix, encoded = sub_id.split("_", 1)
    n = _crockford_decode(encoded)
    return str(uuid.UUID(bytes=n.to_bytes(16, "big")))


def uuid_to_sub(uuid_str: str) -> str:
    """Convert e.g. 'aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb' → 'sub_5anaxvqk6cvqeyxvqzzynanexv'"""
    n = int(uuid.UUID(uuid_str).hex, 16)
    return f"sub_{_crockford_encode(n)}"
