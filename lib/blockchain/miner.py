from block import Block
from merkle_tree import MerkleTree
from transaction import Transaction
from samson.core.base_object import BaseObject

class Miner(BaseObject):
    def __init__(self, blockchain: 'BlockChain', account: 'Account', nonce_start: int=None):
        self.blockchain  = blockchain
        self.account     = account
        self.nonce_start = random_int(2**self.blockchain.nonce_size) if nonce_start is None else nonce_start
    

    def mine(self, transactions: list, previous_hash: bytes=None):
        h             = None
        nonce         = self.nonce_start
        previous_hash = previous_hash or self.blockchain.blocks[-1].hash()

        while True:
            h = self.blockchain.H.hash(previous_hash + self.blockchain.zfill_nonce(nonce))

            if self.blockchain.check_length(h):
                # Create a new block and award self a coin
                award = Transaction.create(
                    blockchain=self.blockchain,
                    ins=[],
                    out_mapping={self.account: self.blockchain.mining_award},
                    sender=self.account
                )

                mt = MerkleTree(self.blockchain.H.hash)
                for transaction in transactions + [award]:
                    mt.add_leaf(transaction)

                block = Block(
                    blockchain=self.blockchain,
                    data=mt.root,
                    finder=self.account,
                    previous_hash=previous_hash,
                    nonce=nonce,
                    proof=h
                )

                self.blockchain.receive_block(transactions + [award], block)
                break
            else:
                nonce += 1


    def verify_block(self, block):
        block.verify()

