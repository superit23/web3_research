from samson.utilities.bytes import Bytes
from exceptions import InvalidBlockProofException
from samson.core.base_object import BaseObject
import time

class Block(BaseObject):
    def __init__(self, blockchain: 'BlockChain', finder: 'Account', data: bytes, previous_hash: bytes, nonce: int, proof: bytes):
        self.blockchain    = blockchain
        self.data          = data
        self.previous_hash = previous_hash
        self.nonce         = nonce
        self.proof         = proof
        self.finder        = finder
        self.timestamp     = int(time.time())
    

    def hash(self):
        ser  = self.previous_hash
        ser += self.blockchain.zfill_nonce(self.nonce)
        ser += self.proof
        ser += self.finder.pub_data()
        ser += Bytes.wrap(self.timestamp).zfill(4)
        ser += self.data
        return self.blockchain.H.hash(ser)


    def verify(self):
        try:
            assert self.blockchain.check_length(self.proof)
            assert self.blockchain.H.hash(self.previous_hash + self.blockchain.zfill_nonce(self.nonce)) == self.proof
        except AssertionError:
            raise InvalidBlockProofException

