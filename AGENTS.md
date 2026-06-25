# AGENTS.md — how to write code in this repo

Adopt the **ponytail** philosophy (https://github.com/DietrichGebert/ponytail):
write like a lazy senior developer. The best code is the code you didn't write.
He says nothing. He writes one line. It works.

## The decision ladder — stop at the first rung that solves it

Before writing any new code, walk down this ladder and stop as early as possible:

1. **Does it need to exist?** — Can we skip the feature, delete instead of add, or
   say no? The cheapest code is none.
2. **Already in the codebase?** — Reuse an existing function/scraper/util. This repo
   has a `BaseScraper`, filter pipeline, `JobDB`, `fetch_with_retry`, etc. Check first.
3. **In the standard library?** — `pathlib`, `sqlite3`, `http.server`, `asyncio`,
   `dataclasses`, `tomllib`. Prefer stdlib over a new dependency.
4. **A native platform feature?** — launchd, `caffeinate`, `pgrep`, cron. We already
   lean on these instead of reimplementing schedulers/keep-alive in Python.
5. **An already-installed dependency?** — httpx, rapidfuzz, BeautifulSoup, Jinja2,
   anthropic. Don't add a package when one we have already does it.
6. **Can it be one line?** — A comprehension, a `dict.get`, a small regex beats a
   new helper + tests for it.
7. **Only then:** write the minimal necessary code.

## Never compromise on (these are not "extra code")

Minimalism is about avoiding *unnecessary* code, never about cutting corners on:
- **Validation & error handling** — network calls retry/timeout; parsers guard bad data.
- **Security** — secrets stay in `.env` (gitignored); no PII in the public repo
  (see `.gitignore`: resumes, profile YAMLs, DB are excluded).
- **Correctness** — a one-liner that's wrong is worse than ten lines that work.

## Repo-specific notes

- One-off discovery/probe scripts live in `scripts/` and are disposable — don't grow
  them into frameworks.
- Config over code: companies, role lanes, and thresholds live in `config/`. Prefer
  editing config to adding code paths.
- Heavy imports (e.g. `anthropic`) are imported lazily where used, not at module top,
  to keep startup fast.

When in doubt: delete, reuse, or write one line. Then stop.
