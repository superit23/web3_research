import time
import struct

class BlockChain(BaseObject):
    def __init__(self, hardness: int=5, avg_mine_time: int=600, H: 'Hash'=None, nonce_size: int=128, mining_award: float=25.0):
        self.hardness      = 2**hardness
        self.avg_mine_time = avg_mine_time
        self.H             = H or SHA256()
        self.nonce_size    = nonce_size
        self.mining_award  = mining_award
        self.miners        = [Miner(blockchain=self, nonce_start=0, account=Account(self))]
        self.blocks        = []
        self.transactions  = {}
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
        self.hardness *= self.avg_mine_time / actual_avg_mine
        self.hardness  = max(self.hardness, 2**5)


    def receive_block(self, block: 'Block'):
        for miner in self.miners:
            miner.verify_block(block)

        self.blocks.append(block)

        # Apply transactions
        for trans in block.transactions:
            try:
                trans.verify(block)

                for in_coin in trans.ins:
                    self.spent_coins.add(in_coin)
                    in_coin.owner.coins.remove(in_coin)

                for out_coin in trans.outs:
                    out_coin.owner.coins.append(out_coin)

                self.transactions[trans.hash()] = (block, trans)
            except Exception as e:
                print(f'Invalid transaction detected: {type(e).__name__}')


        if not len(self.blocks) % 2016:
            self.readjust_mine_time()



class InvalidBlockProofException(Exception):
    pass


class Block(BaseObject):
    def __init__(self, blockchain: 'BlockChain', finder: 'Account', transactions: list, previous_hash: bytes, nonce: int, proof: bytes):
        self.blockchain    = blockchain
        self.transactions  = transactions
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

        for transaction in self.transactions:
            ser += transaction.hash()

        return self.blockchain.H.hash(ser)


    def verify(self):
        try:
            assert self.blockchain.check_length(self.proof)
            assert self.blockchain.H.hash(self.previous_hash + self.blockchain.zfill_nonce(self.nonce)) == self.proof
        except AssertionError:
            raise InvalidBlockProofException


class InvalidSignatureException(Exception):
    pass


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


class InvalidMintException(Exception):
    pass


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



class CoinDoubleSpendException(Exception):
    pass

class UTXOMismatchException(Exception):
    pass

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

                block = Block(
                    blockchain=self.blockchain,
                    transactions=transactions + [award],
                    finder=self.account,
                    previous_hash=previous_hash,
                    nonce=nonce,
                    proof=h
                )

                self.blockchain.receive_block(block)
                break
            else:
                nonce += 1


    def verify_block(self, block):
        block.verify()



def test_blockchain():
    blockchain = BlockChain()
    miner      = blockchain.miners[0]

    # Miner receives mining award
    assert miner.account.worth == blockchain.mining_award

    account2    = Account(blockchain)
    transaction = miner.account.transfer(14.3, account2)

    # Despite the transaction being created, it hasn't been applied
    assert miner.account.worth == blockchain.mining_award
    assert account2.worth == 0.0

    miner.mine([transaction])

    # Transaction is applied and miner gets a second award
    assert miner.account.worth == (blockchain.mining_award*2 - 14.3)
    assert account2.worth == 14.3

    # Double spend
    coin   = miner.account.coins[-1]
    trans1 = Transaction.create(blockchain=blockchain, ins=[coin], out_mapping={account2: 1, miner.account: coin.amount-1})
    trans2 = Transaction.create(blockchain=blockchain, ins=[coin], out_mapping={account2: 1, miner.account: coin.amount-1})
    miner.mine([trans1, trans2])

    # UTXO mismatch
    trans3 = Transaction.create(blockchain=blockchain, ins=[coin], out_mapping={account2: 1, miner.account: coin.amount-2})
    miner.mine([trans3])

    # Invalid signature
    fake_coin = Coin(blockchain=blockchain, amount=1000, signature=Bytes.random(64), owner=account2, transaction=transaction)
    trans4    = Transaction.create(blockchain=blockchain, ins=[fake_coin], out_mapping={account2: fake_coin.amount})
    miner.mine([trans4])

    # Invalid award mint
    fake_award = Transaction.create(
        blockchain=blockchain,
        ins=[],
        out_mapping={account2: blockchain.mining_award},
        sender=account2
    )
    miner.mine([fake_award])

    # Inject fake block
    try:
        block = Block(
            blockchain=blockchain,
            transactions=[fake_award],
            finder=account2,
            previous_hash=blockchain.blocks[-1].hash(),
            nonce=0,
            proof=Bytes.random(20).zfill(32)
        )

        blockchain.receive_block(block)
    except InvalidBlockProofException:
        print("InvalidBlockProofException")
