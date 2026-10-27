#!/usr/bin/env python3
"""Prepare a local verifier; never persist the plaintext password."""
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path

def main():
    os.umask(0o077)
    target = Path.home() / '.local/share/pubster/secrets'
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.chmod(0o700)
    path = target / 'password-verifier.json'
    if path.exists():
        raise SystemExit('Verifier already exists; explicit rotation required.')
    password = getpass.getpass('Pubster password: ').encode('utf-8')
    salt = os.urandom(32)
    key = hashlib.scrypt(password, salt=salt, n=32768, r=8, p=3, dklen=32, maxmem=64*1024*1024)
    del password
    verifier = dict(version=1, algorithm='scrypt', N=32768, r=8, p=3,
                    salt_b64=base64.b64encode(salt).decode(),
                    key_b64=base64.b64encode(key).decode())
    with path.open('x') as output:
        json.dump(verifier, output)
    assert path.stat().st_mode & 0o777 == 0o600
    print('Local verifier stored with mode 0600. Not deployed to Cloudflare.')

if __name__ == '__main__':
    main()
