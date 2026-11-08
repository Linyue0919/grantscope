"""Authenticated encrypted durability for a separately protected POSIX research store."""
import base64
import json
import os
from pathlib import Path
import tempfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

HEADER = b'GSRC01'
MAX_BYTES = 32 * 1024 * 1024


class EncryptedResearchArchive:
    def __init__(self, root, encoded_key):
        self.root = Path(root)
        try:
            key = base64.b64decode(encoded_key or '', altchars=b'-_', validate=True)
        except (ValueError, TypeError):
            raise ValueError('Research archive requires a valid encryption key') from None
        if len(key) != 32:
            raise ValueError('Research archive requires a 32-byte encryption key')
        self.cipher = AESGCM(key)

    def _path(self, scope):
        if len(scope) != 64 or any(c not in '0123456789abcdef' for c in scope):
            raise ValueError('Invalid research scope')
        if self.root.is_symlink():
            raise ValueError('Research archive must not be a symlink')
        path = self.root / (scope + '.aesgcm')
        if path.is_symlink():
            raise ValueError('Research archive entry must not be a symlink')
        return path

    def load(self, scope):
        path = self._path(scope)
        if not path.exists():
            return None
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Encrypted research archive exceeds size limit')
        blob = path.read_bytes()
        if not blob.startswith(HEADER) or len(blob) < len(HEADER) + 12 + 16:
            raise ValueError('Invalid encrypted research archive')
        try:
            raw = self.cipher.decrypt(blob[6:18], blob[18:], b'GrantScope-research-v1:' + scope.encode())
            records = json.loads(raw)
        except (InvalidTag, ValueError, UnicodeError):
            raise ValueError('Research archive authentication failed; data not loaded') from None
        if not isinstance(records, dict):
            raise ValueError('Invalid research archive record structure')
        return records

    def save(self, scope, records):
        path = self._path(scope)
        raw = json.dumps(records, ensure_ascii=False).encode()
        if len(raw) + 34 > MAX_BYTES:
            raise ValueError('Research archive exceeds size limit')
        nonce = os.urandom(12)
        blob = HEADER + nonce + self.cipher.encrypt(nonce, raw, b'GrantScope-research-v1:' + scope.encode())
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(scope)
        fd, name = tempfile.mkstemp(prefix=scope + '.', suffix='.tmp', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
