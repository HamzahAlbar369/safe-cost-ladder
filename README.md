# engine — Deliver AI with Less Compute (HUMAIN × Misk Hackathon, Challenge 2)

An efficiency layer that answers each request with the cheapest (model, effort) configuration that still
meets the task's accuracy floor and latency budget, and proves the savings on held-out data.

> **Fiction disclaimer.** The showcase workload is a *fictional* motor-insurance claims desk
> ("Oasis Motor Insurance (fictional demo insurer)"). Its rules are invented for this demo and are not
> real Najm, SAMA or insurer rules.

Status: Phase 0 (recon & smoke). See `docs/SPEC.md` and `docs/DECISIONS.md`.

```
uv sync
uv run engine check
```
