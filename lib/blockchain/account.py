from exceptions import InvalidSignatureException
from transaction import Transaction
from samson.public_key.ecdsa import ECDSA
from samson.utilities.bytes import Bytes
from samson.core.base_object import BaseObject
from samson.math.algebra.curves.named import P256

class Account(BaseObject):
    def __init__(self, blockchain: 'BlockChain'):
        self.blockchain = blockchain
        self.coins      = []
        self.key        = ECDSA(P256.G)


    @property
    def id(self):
        return Bytes(self.pub_data()[:20].hex().upper())


    @property
    def worth(self):
        return sum([c.amount for c in self.coins], 0.0)


    def __reprdir__(self):
        return ['id', 'worth']


    def __hash__(self):
        return hash(self.pub_data())


    def pub_data(self):
        return self.key.Q.serialize_compressed()


    def sign(self, data: bytes):
        r,s = self.key.sign(data)
        return Bytes(r).zfill(32) + Bytes(s).zfill(32)


    def verify(self, data: bytes, signature: bytes):
        r,s = signature.chunk(32)
        if not self.key.verify(data, (r.int(), s.int())):
            raise InvalidSignatureException


    def receive_coin(self, coin: 'Coin'):
        self.coins.append(coin)


    def transfer(self, amount: float, recipient: 'Account'):
        total    = 0.0
        to_spend = []

        # Collect the coins we need to spend; make sure we have enough
        for coin in self.coins:
            to_spend.append(coin)
            total += coin.amount

            if total >= amount:
                break

        assert total >= amount

        out_mapping = {recipient: amount, self: total-amount}
        return Transaction.create(blockchain=self.blockchain, ins=to_spend, out_mapping=out_mapping)
