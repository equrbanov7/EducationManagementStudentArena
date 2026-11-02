"""Authenticated encrypted export; plaintext stays in memory, caller pins recipient key."""

import base64
import hashlib
import json
import os

from django.core.serializers.json import DjangoJSONEncoder

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_export(snapshot, public_key_bytes, *, fingerprint, error_class=ValueError):
    public = serialization.load_pem_public_key(public_key_bytes)
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
        raise error_class("rsa_key_invalid")
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != fingerprint:
        raise error_class("public_key_fingerprint_mismatch")
    plaintext = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    metadata = {
        "format": "wcu-workload-envelope/1",
        "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
        "key_sha256": fingerprint,
    }
    aad = json.dumps(metadata, sort_keys=True).encode()
    wrapped = public.encrypt(
        key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return {
        **metadata,
        "nonce": base64.b64encode(nonce).decode(),
        "wrapped_key": base64.b64encode(wrapped).decode(),
        "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, plaintext, aad)).decode(),
    }
