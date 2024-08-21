# Damn Vulnerable DeFi v4
Location: [https://www.damnvulnerabledefi.xyz](https://www.damnvulnerabledefi.xyz)

## 1. Unstoppable
```
There’s a tokenized vault with a million DVT tokens deposited. It’s offering flash loans for free, until the grace period ends.

To catch any bugs before going 100% permissionless, the developers decided to run a live beta in testnet. There’s a monitoring contract to check liveness of the flashloan feature.

Starting with 10 DVT tokens in balance, show that it’s possible to halt the vault. It must stop offering flash loans.
```

```solidity
    if (convertToShares(totalSupply) != balanceBefore) revert InvalidBalance(); // enforce ERC4626 requirement
```

## 2. Naive receiver
```
There’s a pool with 1000 WETH in balance offering flash loans. It has a fixed fee of 1 WETH. The pool supports meta-transactions by integrating with a permissionless forwarder contract.

A user deployed a sample contract with 10 WETH in balance. Looks like it can execute flash loans of WETH.

All funds are at risk! Rescue all WETH from the user and the pool, and deposit it into the designated recovery account.
```

## 3. Truster
```
More and more lending pools are offering flashloans. In this case, a new pool has launched that is offering flashloans of DVT tokens for free.

The pool holds 1 million DVT tokens. You have nothing.

To pass this challenge, rescue all funds in the pool executing a single transaction. Deposit the funds into the designated recovery account.
```

## 4. Side entrance
```
A surprisingly simple pool allows anyone to deposit ETH, and withdraw it at any point in time.

It has 1000 ETH in balance already, and is offering free flashloans using the deposited ETH to promote their system.

Yoy start with 1 ETH in balance. Pass the challenge by rescuing all ETH from the pool and depositing it in the designated recovery account.
```

## 5. The Rewarder
```
A contract is distributing rewards of Damn Valuable Tokens and WETH.

To claim rewards, users must prove they’re included in the chosen set of beneficiaries. Don’t worry about gas though. The contract has been optimized and allows claiming multiple tokens in the same transaction.

Alice has claimed her rewards already. You can claim yours too! But you’ve realized there’s a critical vulnerability in the contract.

Save as much funds as you can from the distributor. Transfer all recovered assets to the designated recovery account.
```

## 6. Selfie
```
A new lending pool has launched! It’s now offering flash loans of DVT tokens. It even includes a fancy governance mechanism to control it.

What could go wrong, right ?

You start with no DVT tokens in balance, and the pool has 1.5 million at risk.

Rescue all funds from the pool and deposit them into the designated recovery account.
```

## 7. Compromised
```
While poking around a web service of one of the most popular DeFi projects in the space, you get a strange response from the server. Here’s a snippet:


HTTP/2 200 OK
content-type: text/html
content-language: en
vary: Accept-Encoding
server: cloudflare

4d 48 67 33 5a 44 45 31 59 6d 4a 68 4d 6a 5a 6a 4e 54 49 7a 4e 6a 67 7a 59 6d 5a 6a 4d 32 52 6a 4e 32 4e 6b 59 7a 56 6b 4d 57 49 34 59 54 49 33 4e 44 51 30 4e 44 63 31 4f 54 64 6a 5a 6a 52 6b 59 54 45 33 4d 44 56 6a 5a 6a 5a 6a 4f 54 6b 7a 4d 44 59 7a 4e 7a 51 30

4d 48 67 32 4f 47 4a 6b 4d 44 49 77 59 57 51 78 4f 44 5a 69 4e 6a 51 33 59 54 59 35 4d 57 4d 32 59 54 56 6a 4d 47 4d 78 4e 54 49 35 5a 6a 49 78 5a 57 4e 6b 4d 44 6c 6b 59 32 4d 30 4e 54 49 30 4d 54 51 77 4d 6d 46 6a 4e 6a 42 69 59 54 4d 33 4e 32 4d 30 4d 54 55 35


A related on-chain exchange is selling (absurdly overpriced) collectibles called “DVNFT”, now at 999 ETH each.

This price is fetched from an on-chain oracle, based on 3 trusted reporters: 0x188...088, 0xA41...9D8 and 0xab3...a40.

Starting with just 0.1 ETH in balance, pass the challenge by rescuing all ETH available in the exchange. Then deposit the funds into the designated recovery account.
```

## 8. Puppet
```
There’s a lending pool where users can borrow Damn Valuable Tokens (DVTs). To do so, they first need to deposit twice the borrow amount in ETH as collateral. The pool currently has 100000 DVTs in liquidity.

There’s a DVT market opened in an old Uniswap v1 exchange, currently with 10 ETH and 10 DVT in liquidity.

Pass the challenge by saving all tokens from the lending pool, then depositing them into the designated recovery account. You start with 25 ETH and 1000 DVTs in balance.
```

## 9. Puppetv2
```
The developers of the previous pool seem to have learned the lesson. And released a new version.

Now they’re using a Uniswap v2 exchange as a price oracle, along with the recommended utility libraries. Shouldn’t that be enough?

You start with 20 ETH and 10000 DVT tokens in balance. The pool has a million DVT tokens in balance at risk!

Save all funds from the pool, depositing them into the designated recovery account.
```

## 15. ABI Smuggling
```
There’s a permissioned vault with 1 million DVT tokens deposited. The vault allows withdrawing funds periodically, as well as taking all funds out in case of emergencies.

The contract has an embedded generic authorization scheme, only allowing known accounts to execute specific actions.

The dev team has received a responsible disclosure saying all funds can be stolen.

Rescue all funds from the vault, transferring them to the designated recovery account.
```