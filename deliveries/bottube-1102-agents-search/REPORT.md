# BoTTube bug report — `/agents` ignores `q` search parameter

Target bounty: `Scottcjn/rustchain-bounties#1102` (functional/UI bug reports)

Status: **claim-ready evidence; not yet submitted upstream**

## Summary

The public BoTTube AI Agents directory accepts a `q` query parameter and updates the browser URL after submitting the page-local `Search agents` form, but the directory does not filter the agent list at all.

A deterministic test with a deliberately nonexistent query still returns the complete directory and displays `All Agents (1579)`.

## Reproduction

URL: `https://bottube.ai/agents`

1. Open the AI Agents directory.
2. Enter `nonexistentagent999` in the `Search agents` field.
3. Submit the form.
4. Observe that the URL becomes:
   `https://bottube.ai/agents?q=nonexistentagent999`
5. Observe that the page still shows `All Agents (1579)` and the normal unfiltered directory entries.
6. Reload the page or open the query URL directly. The result is unchanged.

The same behavior reproduced with a real-name query such as `Sophia`.

## Expected

The directory should apply `q` to the agent dataset and show only matching agents. A deliberately nonexistent query should produce zero results or an explicit `No agents found` state.

## Actual

The query is ignored. The complete directory is rendered regardless of the submitted search string.

## Browser-visible evidence

- Search submission changes the URL to include the requested `q` value.
- With `q=nonexistentagent999`, the primary directory heading still reads `All Agents (1579)`.
- Known unrelated agents such as `@sophia-elya` and `@the_daily_byte` remain visible.
- Repeated reloads and different search terms produce the same unfiltered result.

## Determinism

Reproduced repeatedly in a live browser session on 2026-09-11. Behavior was stable across direct navigation and form submission.

## Duplicate check

The closest existing reports found are different surfaces:

- `Scottcjn/bottube#1208` — public `GET /api/search` ignores documented `tag` and `agent` filters. That issue concerns the video search API, not the `/agents` directory `q` parameter.
- `Scottcjn/bottube#1368` and `#1216` — accessibility reports for the `/agents` page-local search input lacking a programmatic label. They do not report that search filtering itself is nonfunctional.

A search for an existing issue specifically describing `/agents?q=...` being ignored did not return a matching report.

## Impact

This is a functional discovery failure: users cannot narrow the 1,579-agent directory through the search UI even though the form and query parameter imply that filtering is supported. This also makes the page misleading for clients or users who assume the URL represents a filtered view.

## Suggested fix direction

Inspect the `/agents` route and ensure `request.args.get("q")` is used to constrain the directory query (case-insensitive name/display-name search is sufficient for the existing UI contract). Add a regression test covering both a positive match and a deliberately nonexistent query.

## Claim state

Do **not** treat this file as payout evidence or upstream acceptance. Native GitHub submission is currently blocked because the available browser profile is not authenticated and the installed GitHub integration has no write permission to `Scottcjn/rustchain-bounties` / `Scottcjn/bottube`.
