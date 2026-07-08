# Pharma Portfolio Mining

Mine the investigational portfolios of the top 20 pharmas to extract drug/disease associations, therapeutic area alignment, and trending targets.

- **Documentation**: [GitHub Pages](https://opentargets.github.io/hackathon_pharma_portfolio/)
- **Project board**: [Issue tracker](https://github.com/orgs/opentargets/projects/54)

## Extracting a new pharma

See [`instruction_for_agent.md`](instruction_for_agent.md) for the full workflow.
Example prompt to hand to the agent for the next company:

> Let's do `<Company>` next. Check `docs/sources.md` for its tier and source
> URL. Follow `instruction_for_agent.md`: if it's Tier 1/2, find/confirm the
> raw source file; if it's Tier 3, scrape it first (raw, unmapped) and open a
> GitHub issue documenting the scrape. Either way, ask me about field-mapping
> decisions one by one before writing the conversion script — don't guess.
> Save everything (source file, `schema.py`, converter, `log.md`, parquet) in
> `pharmas/<company>/`, then mark it Done in `docs/sources.md`.
