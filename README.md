# TunePact

Escrow and dispute resolution for commissioned AI model fine-tunes, built as a GenLayer Intelligent Contract.

A buyer locks GEN for a trainer. The trainer delivers a Hugging Face commit SHA. The contract fetches the repository metadata pinned to that commit, checks hard anchors in plain code (repository id, resolved commit, weights file prefix, minimum size, base model, license, optional sha256) and asks validators to judge the model card against the task specification. A positive verdict is impossible unless every anchor matched and the model quoted text that really exists in the fetched README. Either party can appeal to a staked commit-reveal jury.

- Contract address (Studio, production variant): `0x1E6Fc52A570abb1E84B55a17C4aB114D9EA876A2`
- Contract address (Studio, testnet variant, used for the live test runs below): `0x4216f3849aFf00B5DBE46107464e4d4050310D4f`
- Live demo: https://123cryp.github.io/tunepact/frontend/

## Files

| Path | Purpose |
|---|---|
| `contracts/tunepact.py` | documented source |
| `contracts/tunepact_deploy.py` | comment-free file for GenLayer Studio (generated) |
| `contracts/tunepact_testnet.py` | same logic with short windows for live testing (generated) |
| `tools/build_deploy.py` | generates the two files above (AST based) |
| `tools/hf_probe.py` | tiny diagnostic contract that shows the real Hugging Face API response |
| `tests/` | offline GenLayer stub and 150+ tests |
| `frontend/index.html` | single-file UI, no build step |
| `docs/` | architecture, lessons, portal text |

## Variants

`tunepact_deploy.py` and `tunepact_testnet.py` contain exactly the same logic. They differ only in seven timing and size constants, so the full flow can be exercised in minutes on the testnet variant.

| Constant | testnet | production |
|---|---|---|
| Delivery deadline | 15 minutes | 7 days |
| Challenge window | 2 minutes | 1 day |
| Jury commit window | 3 minutes | 12 hours |
| Jury reveal window | 3 minutes | 12 hours |
| Stuck-deal recovery timeout | 20 minutes | 7 days |
| Round 1 jury size | 1 | 3 |
| Round 2 jury size | 3 | 5 |

## Flow

1. `create_deal` (optionally funded) then `fund_deal`.
2. Trainer calls `submit_delivery` with a 40-char commit SHA.
3. Anyone calls `run_tier1_verdict`. Result is DELIVERED, PARTIALLY_DELIVERED, NOT_DELIVERED or UNDETERMINED.
4. During the challenge window either party can `escalate_to_jury` with a bond. Jurors `commit_jury_vote` then `reveal_jury_vote`. Round 1 has 3 jurors, a split escalates to 5 fresh jurors, a second split falls back to the Tier-1 verdict.
5. After the window `finalize_unappealed` pays out. Everything is credited to a pull balance; call `withdraw`.

Payouts: DELIVERED pays the trainer minus a 1% fee. PARTIALLY_DELIVERED splits 50/50 (fee on the trainer half). Otherwise the buyer is refunded. Timeouts and stuck deals have exit paths.

## Run the tests

```
python3 tools/build_deploy.py
python3 -m unittest discover -s tests
```

No pip packages are required.

## Deploy

Paste `contracts/tunepact_deploy.py` (or `tunepact_testnet.py` for fast windows) into GenLayer Studio and deploy with no constructor arguments. Put the address into `CONFIG.CONTRACT_ADDRESS` at the top of `frontend/index.html`.

## Status

Verified live on GenLayer Studio with the testnet variant:

| Path | Result |
|---|---|
| Hugging Face API fetch and anchor parsing | works against real repositories |
| Anchor mismatch | UNDETERMINED, buyer refunded, LLM not called |
| Matching fine-tune (Sohamb2005/gpt2-finetuned-apologies) | DELIVERED with an exact README quote |
| Trainer payout, buyer refund, 1% fee, treasury withdrawal | all paid out; accounting balanced; contract balance returned to 0 |
| Jury appeal (deal 4) | juror registration, appeal bond, commit-reveal vote, jury overturned UNDETERMINED to DELIVERED, bond paid to the winning juror, trainer paid, jurors deregistered and refunded; contract balance returned to 0 |

Verified offline only (150+ tests): jury escalation to a second round, juror slashing for no-reveal, and the stuck-deal recovery paths. The live jury test used the testnet variant (1-juror first round).

Note: invalid calls return an `ERR_*` string instead of reverting, so a SUCCESS transaction does not by itself mean the action happened. Read the return value.
