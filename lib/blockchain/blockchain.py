from samson.utilities.bytes import Bytes
from samson.hashes.sha2 import SHA256
from samson.core.base_object import BaseObject
from miner import Miner
from account import Account

class BlockChain(BaseObject):
    def __init__(self, hardness: int=5, avg_mine_time: int=600, H: 'Hash'=None, nonce_size: int=128, mining_award: float=25.0):
        self.hardness      = 2**hardness
        self.avg_mine_time = avg_mine_time
        self.H             = H or SHA256()
        self.nonce_size    = nonce_size
        self.mining_award  = mining_award
        self.miners        = [Miner(blockchain=self, nonce_start=0, account=Account(self))]
        self.blocks        = []
        self.spent_coins   = set()

        # Mine genesis block
        seed_hash = Bytes.random()
        self.miners[0].mine(transactions=[], previous_hash=seed_hash)


    def __reprdir__(self):
        return ['hardness', 'avg_mine_time', 'nonce_size', 'mining_award']


    def zfill_nonce(self, b):
        return Bytes.wrap(b).zfill(self.nonce_size // 8)
    

    def check_length(self, h: Bytes):
        return h.int() < (2**int(self.H.OUTPUT_SIZE) / self.hardness)


    def readjust_mine_time(self):
        actual_avg_mine = (self.blocks[-1].timestamp - self.blocks[-2016].timestamp) / 2016
        self.hardness  *= self.avg_mine_time / actual_avg_mine
        self.hardness   = max(self.hardness, 2**5)


    def receive_block(self, transactions: 'List[Transactions]', block: 'Block'):
        for miner in self.miners:
            miner.verify_block(block)

        self.blocks.append(block)

        # Apply transactions
        for trans in transactions:
            try:
                trans.verify(block)

                for in_coin in trans.ins:
                    self.spent_coins.add(in_coin)
                    in_coin.owner.coins.remove(in_coin)

                for out_coin in trans.outs:
                    out_coin.owner.coins.append(out_coin)

            except Exception as e:
                print(f'Invalid transaction detected: {type(e).__name__}')


        if not len(self.blocks) % 2016:
            self.readjust_mine_time()
