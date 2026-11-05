# TunePact

Escrow and dispute resolution for commissioned AI model fine-tunes, built as a GenLayer Intelligent Contract.

A buyer locks GEN for a trainer. The trainer delivers a Hugging Face commit SHA. The contract fetches the repository metadata pinned to that commit, checks hard anchors in plain code (repository id, resolved commit, weights file prefix, minimum size, base model, license, optional sha256) and asks validators to judge the model card against the task specification. A positive verdict is impossible unless every anchor matched and the model quoted text that really exists in the fetched README. Either party can appeal to a staked commit-reveal jury.

- Contract address: `TBD after Studio deploy`
- Live demo: `TBD`

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

The contract logic is covered offline. The Hugging Face API response shape and the GEN payout interface are assumptions that must be confirmed on Studio; see `docs/ARCHITECTURE.md` (Known limits) and run `tools/hf_probe.py` first.
