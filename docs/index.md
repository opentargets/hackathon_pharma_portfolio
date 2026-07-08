---
title: Overview
nav_order: 1
---

# Pharma Portfolio Mining — Overview

## Aim

Extract, normalize, and integrate drug/disease associations from the investigational portfolios of the top 20 global pharmaceutical companies. The goal is to understand:

- Which therapeutic areas each company prioritises
- Which targets/MoAs are trending vs. fading
- Overlap and white space across industry pipelines
- Novel vs. "me-too" mechanisms per indication

## Scope

Top 20 pharmas by R&D spend / revenue. Most publish a pipeline tracker for IR purposes — typically showing phase, indication, and sometimes target/MoA for each candidate.

## Caveats & Limitations

| Caveat | Implication |
|---|---|
| **Inconsistent structure** | Each company uses its own format, taxonomy, and level of detail. No single parser works for all. |
| **JS-rendered widgets** | Several pipelines (Tier 3) rely on interactive JavaScript — data must be extracted from network-layer JSON or via Playwright, not from static HTML. |
| **PDF redesigns** | PDF layouts change periodically. A parser built today may break in 6–12 months. |
| **Phase variability** | Some pipelines include preclinical; others start at Phase 1. Definition of "Phase 2" vs. "Phase 2/3" varies. |
| **Partial disclosure** | Some companies (e.g. Merck & Co.) omit Phase 1 candidates. Others exclude partnered assets. |
| **Temporal snapshots** | Pipelines update quarterly or annually. The extracted data is a point-in-time snapshot. |
| **Commercial sensitivity** | Early-stage or strategically sensitive assets may be withheld from public pipelines. |

👉 See [`docs/sources`](sources.md) to see more about each company's pipeline.  
👉 See [`setup.md`](setup.md) for environment setup and tool installation.