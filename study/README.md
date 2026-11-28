# The measurement behind QUOTE_CHECK.md

These are the scripts that produced the quote check, as they ran from 26 to 28 Nov 2026, with a 45-minute sample of their output so the analysis can be re-run without a key and without a network.

```
verif/cotes_cmc.py   CMC quotes of 15 perpetuals on every exchange (15 credits per snapshot)
verif/carnets.py     best bid, best ask, last, mark and index from 11 exchanges' public endpoints (every 30 s)
verif/contexte.py    funding, depth for $1,000 and $10,000 on 50 levels, deposits and withdrawals (every 5 min)
verif/htx_hotes.py   the two public HTX hosts, side by side (every minute)
verif/qualite.py     the analysis: reads the three files, calls nothing, writes runs/quality_report.md and .json
cmc_spread/          the small CMC client the sampler uses (key from CMC_API_KEY or a .env file, credit guard, call log)
config.json          the 15 tokens and their CMC ids
runs/sample_*.jsonl  45 minutes of real data (27 Nov 2026, 08:00 to 08:45 UTC)
```

Re-run the analysis on the sample (0 credit):

```bash
python3 verif/qualite.py cmc=sample_cmc.jsonl books=sample_books.jsonl ctx=sample_ctx.jsonl
```

Sample more data yourself (the CMC sampler needs a key; the other three need nothing):

```bash
CMC_ENV_FILE=../.env python3 verif/cotes_cmc.py --snapshots 24 --every 150 --max-credits 400 --reserve 1000 --out my_cmc.jsonl
python3 verif/carnets.py --rounds 120 --every 30 --out my_books.jsonl
python3 verif/contexte.py --cycles 12 --every 300 --out my_ctx.jsonl
python3 verif/qualite.py cmc=my_cmc.jsonl books=my_books.jsonl ctx=my_ctx.jsonl
```

Public market data only on the exchange side: no account, no exchange key, no order. The file names are French because the study was written in French: `carnets` = order books, `cotes` = quotes, `contexte` = context, `qualite` = quality.
