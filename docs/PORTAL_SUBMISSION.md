# Portal submission

Repository: https://github.com/123Cryp/tunepact
Live demo: https://123cryp.github.io/tunepact/frontend/

Title: TunePact - escrow for AI model fine-tunes

Short description: Buyers lock GEN, trainers deliver a pinned Hugging Face commit, and an Intelligent Contract checks hard anchors plus the model card before paying out, with a staked commit-reveal jury for appeals.

## How to verify (exercise the paths)
1. Deploy `contracts/tunepact_testnet.py` (short windows, same logic as the production file) or use the already deployed contracts below. Call `get_config`.
2. With wallet A call `create_deal` funded 1 GEN for a public Hugging Face repo with real anchors; wallet B (trainer) calls `submit_delivery` with the repo's current commit SHA.
3. Call `run_tier1_verdict` and read `get_deal` and `get_deal_for_jury` (observed commit, size, base model, license, quote).
4. After the short challenge window call `finalize_unappealed`, then `withdraw` from the paid wallet and check `get_accounting.balanced`.
5. Repeat with a wrong base-model anchor and confirm the verdict is UNDETERMINED and the buyer is refunded.
6. Optional: register jurors, appeal, commit and reveal votes.

Evidence links: huggingface.co model API and raw README for the repo used.
Tags: escrow, ai, huggingface, dispute-resolution, jury

## Live verification already performed (Studio)
- Production contract: 0x1E6Fc52A570abb1E84B55a17C4aB114D9EA876A2 (`tunepact_deploy.py`, official address)
- Demo contract used for the live runs below: 0x4216f3849aFf00B5DBE46107464e4d4050310D4f (`tunepact_testnet.py`; identical logic, only seven timing and jury-size constants differ, see README)
- Deal 1 and 2: anchor mismatch (base model) -> UNDETERMINED -> buyer refunded.
- Deal 3: Sohamb2005/gpt2-finetuned-apologies at commit 9a8478a11bc87deabf274ea65b769576389d5b72 -> DELIVERED with quoted README evidence -> trainer paid 0.99 GEN, 0.01 GEN fee to treasury.
- get_accounting stayed balanced throughout and ended at a contract balance of 0.
- Deal 4 (jury path): four wallets registered as jurors, Tier-1 returned UNDETERMINED (deliberately wrong base-model anchor), the trainer appealed with a 5 GEN bond, the selected juror committed and revealed DELIVERED, the deal finalized as DELIVERED, the bond went to the winning juror, the trainer was paid, all jurors deregistered and withdrew, and get_accounting ended balanced with a contract balance of 0.
