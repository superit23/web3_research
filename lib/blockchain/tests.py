from blockchain import BlockChain
from miner import Miner
from account import Account
from block import Block
from transaction import Transaction
from merkle_tree import MerkleTree
from coin import Coin
from samson.utilities.bytes import Bytes
from exceptions import InvalidBlockProofException

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
        mt = MerkleTree(blockchain.H.hash)
        mt.add_leaf(fake_award)

        block = Block(
            blockchain=blockchain,
            data=mt.root,
            finder=account2,
            previous_hash=blockchain.blocks[-1].hash(),
            nonce=0,
            proof=Bytes.random(20).zfill(32)
        )

        blockchain.receive_block([fake_award], block)
    except InvalidBlockProofException:
        print("InvalidBlockProofException")


test_blockchain()