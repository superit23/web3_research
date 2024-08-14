import struct
from samson.core.base_object import BaseObject
from exceptions import InvalidMintException

class Coin(BaseObject):
    def __init__(self, blockchain: 'BlockChain', amount: float, signature: bytes, transaction: 'Transaction', owner: 'Account'):
        self.blockchain  = blockchain
        self.amount      = amount
        self.signature   = signature
        self.transaction = transaction
        self.owner       = owner
    

    def __hash__(self):
        return hash(self.signature)


    @property
    def trans_hash(self):
        return self.transaction.hash()


    @property
    def owner_id(self):
        return self.owner.id


    def __reprdir__(self):
        return ['amount', 'owner_id', 'trans_hash']


    @staticmethod
    def mint(blockchain: 'BlockChain', sender: 'Account', recipient: 'Account', amount: float, transaction: 'Transaction'):
        b_amount  = struct.pack('f', amount)
        to_sign   = b_amount + transaction.hash() + recipient.pub_data()
        signature = sender.sign(to_sign)

        return Coin(blockchain=blockchain, amount=amount, signature=signature, owner=recipient, transaction=transaction)


    def verify(self, block: 'Block'):
        b_amount  = struct.pack('f', self.amount)
        to_verify = b_amount + self.transaction.hash() + self.owner.pub_data()

        # Normal transaction
        if self.transaction.ins:
            self.transaction.ins[0].owner.verify(to_verify, self.signature)

            for in_coin in self.transaction.ins:
                in_coin.verify(block)

        # Coin initial minting
        else:
            try:
                assert len(self.transaction.outs) == 1
                assert self.transaction.outs[0].owner == block.finder
                self.transaction.outs[0].owner.verify(to_verify, self.signature)
            except Exception as e:
                raise InvalidMintException from e
