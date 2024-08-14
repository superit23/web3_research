class InvalidSignatureException(Exception):
    pass

class InvalidBlockProofException(Exception):
    pass

class InvalidMintException(Exception):
    pass

class CoinDoubleSpendException(Exception):
    pass

class UTXOMismatchException(Exception):
    pass
