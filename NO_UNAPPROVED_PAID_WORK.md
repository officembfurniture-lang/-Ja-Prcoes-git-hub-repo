# No unapproved paid work or financial commitments

Status: repository policy proposal, 2026-10-09. Applies to repository automation, agents, maintainers acting on behalf of the owner, and delegated workflows. It does not bind unrelated third parties or amend their contracts.

## Default: no authorization to incur costs

No agent, automation, collaborator, or delegated process may, in the repository owner's name, commission or solicit work that may create a claim for compensation; engage contractors; accept paid terms; start paid trials that renew; incur usage-based API/compute/cloud charges; pay deposits, fees, gas, bounties or reimbursements; borrow; or make binding financial promises **without fresh, specific approval by the owner for the exact action and maximum cost**. Historical broad instructions, repository access, a pull request, issue assignment, or silence are **not** authorization to spend.

Unknown or deferred pricing, success fees, third-party expectations of payment, or ambiguous terms must be treated as a blocking condition, not as a zero price. Agents must not invite people to do work while leaving compensation expectations unclear. Do not request unpaid speculative work under a misleading suggestion of future compensation.

Permitted by default: read-only investigation, work using existing no-additional-charge capabilities, local/internal preparation, and genuinely voluntary contributions with no expectation of payment, provided no new charge or binding obligation is incurred. Preserve security, provenance, review, CI, and HOLD/no-promotion gates.

## Required pre-action gate

Before any external work request, service activation, API call with potential incremental cost, or binding acceptance:

1. Identify the counterparty, action, pricing model, maximum total liability, and relevant terms.
2. Confirm that the action is no-additional-charge and creates no compensation expectation, **or** obtain explicit case-specific approval from the owner. Never infer approval.
3. If any part is unknown, stop the action and record `PAYMENT_GATE_BLOCKED` with the evidence and a free alternative. Do not create the commitment while seeking clarification.
4. Record authorization evidence and readback of the actual action; a claimed approval or an internal receipt is not proof of a valid external contract.
5. If an existing alleged invoice or demand is discovered, preserve it for verification; do not acknowledge liability, promise payment, threaten the claimant, or claim the demand was canceled. Route the specific claim for review.

## Review and enforcement

Repository changes and PRs must not silently add billable CI, cloud resources, API endpoints, contractor requests, paid services, or terms acceptance. Any proposal with such effects remains blocked until case-specific authorization. Code reviewers and automation operators must examine workflow and dependency changes for cost exposure.

This is a **preventive control**, not a representation that any person has demanded payment, a retroactive cancellation of a contract, or a guarantee against third-party claims. It does not erase legally valid prior obligations. If a specific unauthorized action is verified, document its agent/action/timestamp and communicate accurately with the identified counterparty without inventing facts.

The existing omega shadow-driver experiment and Issue #2 remain **HOLD** until the independent paired-validation requirements are met. This policy grants no promotion or deployment authority.
