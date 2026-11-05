# Portal submission

Title: TunePact - escrow for AI model fine-tunes

Short description: Buyers lock GEN, trainers deliver a pinned Hugging Face commit, and an Intelligent Contract checks hard anchors plus the model card before paying out, with a staked commit-reveal jury for appeals.

## How to verify (exercise the paths)
1. Deploy `contracts/tunepact_testnet.py`. Call `get_config`.
2. With wallet A call `create_deal` funded 1 GEN for a public Hugging Face repo with real anchors; wallet B (trainer) calls `submit_delivery` with the repo's current commit SHA.
3. Call `run_tier1_verdict` and read `get_deal` and `get_deal_for_jury` (observed commit, size, base model, license, quote).
4. After the short challenge window call `finalize_unappealed`, then `withdraw` from the paid wallet and check `get_accounting.balanced`.
5. Repeat with a wrong base-model anchor and confirm the verdict is UNDETERMINED and the buyer is refunded.
6. Optional: register jurors, appeal, commit and reveal votes.

Evidence links: huggingface.co model API and raw README for the repo used.
Tags: escrow, ai, huggingface, dispute-resolution, jury
