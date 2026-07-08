# Pharma Portfolio Mining

Mine the investigational portfolios of the top 20 pharmas to extract drug/disease associations, therapeutic area alignment, and trending targets.

- **Documentation**: [GitHub Pages](https://opentargets.github.io/hackathon_pharma_portfolio/)
- **Project board**: [Issue tracker](https://github.com/orgs/opentargets/projects/54)

## Scraping (Tier 3 sources)

For pharmas with no static CSV/PDF (Tier 3, see `docs/sources.md`), this repo
ships a `scrapling` Claude Code skill at `.claude/skills/scrapling/` (tracked
in git, so everyone gets the same version — no per-person install needed).
See [`SCRAPLING.md`](SCRAPLING.md) for what it is, how it was set up, and a
verdict on it plus alternative scraping skills considered.

## Extracting a new pharma

See [`instruction_for_agent.md`](instruction_for_agent.md) for the full workflow.
Example prompt to hand to the agent for the next company:

> Let's do `<Company>` next. Check `docs/sources.md` for its tier and source
> URL. Open a GitHub issue documenting the process. Follow
> `instruction_for_agent.md`: check **both** a downloadable file (PDF/CSV)
> and whether the pipeline webpage itself is scrapeable (cheap `curl` first)
> — don't just trust the tier label. Tell me what each source actually
> contains and ask me to confirm which to use; if both exist and both add
> real information, use both (confirm the merge approach with me too). Ask
> me about field-mapping decisions one by one before writing the conversion
> script — don't guess. Save everything (source file(s), converter, `log.md`,
> parquet) in `src/pharmas/<company>/`, importing the shared schema from
> `src/schema.py` (don't copy it in). Before calling it done, ask me to send
> you a manual copy/paste of some of the source data so you can cross-check
> it against your output — report any inconsistency this turns up in both
> `log.md` and the issue. Then mark it Done in `docs/sources.md`. Update the
> issue at the end.
