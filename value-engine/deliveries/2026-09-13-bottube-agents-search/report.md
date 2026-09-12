# BoTTube `/agents` search query is ignored

## Status

Reproduced against the public production site on 2026-09-13. This is an observation/report artifact, not a claim of bounty acceptance or payment.

## Target

- Product: BoTTube
- Public URL: `https://bottube.ai/agents`
- Surface: public agent-directory search
- Mutation performed: none

## Summary

The page-local agent search updates the URL with a `q` query parameter, but the directory is not filtered. A query for a known agent and a query for a deliberately nonexistent string both continue to return the complete directory and display `All Agents (1579)`.

## Reproduction

1. Open `https://bottube.ai/agents`.
2. In the page-local `Search agents` input, enter `Sophia` and submit.
3. Observe that the URL becomes `https://bottube.ai/agents?q=Sophia`, while the full directory remains visible.
4. Repeat with a deliberately nonexistent term such as `nonexistentagent999`.
5. Observe that the URL becomes `https://bottube.ai/agents?q=nonexistentagent999`, but the heading still reads `All Agents (1579)` and normal agents such as `@sophia-elya` and `@the_daily_byte` remain in the list.
6. Refresh/repeat: the behavior remains the same.

## Expected

`q` should filter the agent directory by the submitted search term. A deliberately nonexistent term should return zero matches or a clear `No agents found` state.

## Actual

The query parameter is accepted into the URL but appears to be ignored by the result-generation path; the unfiltered agent directory is returned.

## Determinism

The browser-based production check reproduced the behavior repeatedly with multiple queries and after refresh. No authenticated action, upload, vote, comment, or state-changing request was used.

## Impact

This is a functional discovery/search defect rather than a cosmetic issue. Users and agents cannot reliably narrow the directory by agent name, and clients can falsely infer that a search was applied because the URL contains `q` even though the visible result set is unchanged.

## Duplicate analysis

Known nearby issues were checked before preparing this report:

- `Scottcjn/bottube#1368` — missing accessible label on the `/agents` page search input. Same UI surface, different defect.
- `Scottcjn/bottube#1216` — accessibility report for the same search input. Different defect.
- `Scottcjn/bottube#1208` — public `/api/search` ignores documented `tag` and `agent` filters. Different endpoint and filter contract.

No issue found in the checked results described the page-level `/agents?q=...` query returning the complete unfiltered directory.

## Suggested fix direction

Inspect the `agents_page()` request path and ensure `request.args.get("q")` participates in the database/query filtering before rendering. Add a regression test covering at least:

- a known exact/partial agent-name query;
- a deliberately nonexistent query returning an empty state;
- preservation of the submitted `q` value in the search input;
- pagination operating on the filtered result set rather than the full directory.

## Verification after repair

A repaired production path should satisfy both controls:

- `GET /agents?q=Sophia` returns only matching agents (subject to the intended matching policy).
- `GET /agents?q=nonexistentagent999` does not render the full directory and reports zero matches / an empty state.

## Tooling disclosure

The live reproduction was performed through a browser automation session operating only public, read-only navigation/search interactions. The report and duplicate analysis were prepared with AI assistance. No exploit, destructive test, credential use, or private data access was involved.
