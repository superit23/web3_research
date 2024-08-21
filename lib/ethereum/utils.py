from samson.hashes.keccak import Keccak
from samson.public_key.ecdsa import ECDSA
from samson.math.algebra.curves.named import secp256k1
from samson.core.base_object import BaseObject

keccak256 = Keccak(r=1088, c=512, digest_bit_size=256)

class Wallet(BaseObject):
    def __init__(self, private_key: int=None):
        self.ec = ECDSA(secp256k1.G, d=private_key)
    

    def __reprdir__(self):
        return ['address', 'public_key']


    @property
    def _public_key(self):
        return self.ec.Q.serialize_uncompressed()[1:]

    @property
    def public_key(self):
        return self._public_key.hex()

    @property
    def address(self):
        return keccak256.hash(self._public_key)[-20:].hex()


    def sign(self, msg: bytes):
        return self.ec.sign(msg)
