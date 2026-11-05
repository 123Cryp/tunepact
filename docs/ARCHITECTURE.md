# TunePact architecture

## Decisions
- Domain: delivery of a commissioned AI fine-tune on Hugging Face.
- Evidence: `https://huggingface.co/api/models/{repo}/revision/{sha}?blobs=true` and the raw README at the same revision. Both are server-rendered text/JSON.
- Money is GEN, whole units in the UI, wei in the contract.

## State machine
CREATED -> FUNDED -> SUBMITTED -> TIER1_VERDICT -> FINALIZED | REFUNDED
TIER1_VERDICT -> DISPUTED (appeal) -> FINALIZED | REFUNDED
CREATED -> CANCELLED. FUNDED -> REFUNDED (delivery timeout). Any non-terminal state -> terminal through `recover_stuck_deal` after the stuck timeout.

## Tier 1
Leader fetches API JSON and README, runs `parse_hf_evidence` (pure code), and only when all anchors match asks the LLM for a verdict plus an exact quote from the README. Validators repeat the fetch and evaluation and require an exact match on the verdict and the observed facts. A verdict of DELIVERED or PARTIAL is impossible without an anchor match and a real quote. A fetch failure never settles a deal; it only consumes one of three attempts.

## Tier 2
Jurors stake a bond and pay a non-refundable registration fee. Selection is a deterministic hash over the sorted eligible pool; only jurors registered before the Tier-1 snapshot and not party to the deal can be picked. Commit-reveal votes, majority is `votes*2 > revealed`, quorum is `size//2+1`. Jurors who do not reveal lose 5 GEN to the treasury. The appeal bond goes to winning jurors (remainder to the treasury) when a majority forms, to the treasury when the jury cannot decide.

## Accounting invariant
`contract_balance == escrow + withdrawable + juror bonds + appeal bonds + treasury`, exposed by `get_accounting`.

## Trust model
Trusted: the Hugging Face API for the pinned commit, GenLayer validator consensus. Untrusted: README text (isolated in the prompt and bounded), both parties, individual jurors.

## Known limits
- The Hugging Face response shape (`siblings[].lfs.sha256`, `cardData`, `tags`) is unverified live; run `tools/hf_probe.py`.
- Payout uses an EVM interface `emit_transfer` to wallets and is unverified live.
- A repository could be edited after delivery only through new commits; the pinned SHA prevents that for the delivered revision.
- Quality of a model is judged from its model card, not by running it.
