from coin import Coin
from exceptions import UTXOMismatchException, CoinDoubleSpendException
from samson.core.base_object import BaseObject

class Transaction(BaseObject):
    def __init__(self, blockchain: 'BlockChain', ins: list, outs: list):
        self.blockchain = blockchain
        self.ins        = ins
        self.outs       = outs


    def hash(self):
        return self.blockchain.H.hash(b''.join([c.signature for c in self.ins]))


    @staticmethod
    def create(blockchain: 'BlockChain', ins: 'Coin', out_mapping: 'dict[Account, float]', sender: 'Account'=None):
        next_trans = Transaction(blockchain, ins, [])

        for recipient, amount in out_mapping.items():
            next_trans.outs.append(Coin.mint(
                blockchain=blockchain,
                sender=sender or ins[0].owner,
                recipient=recipient,
                amount=amount,
                transaction=next_trans
            ))

        return next_trans


    def verify(self, block: 'Block'):
        if self.ins and (sum([c.amount for c in self.ins]) != sum([c.amount for c in self.outs])):
            raise UTXOMismatchException

        for in_coin in self.ins:
            in_coin.verify(block)

            if in_coin in self.blockchain.spent_coins:
                raise CoinDoubleSpendException

        for out_coin in self.outs:
            out_coin.verify(block)
