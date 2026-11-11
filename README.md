# 13F Intelligence: free automated edition

A static, mobile-friendly hedge-fund 13F dashboard with GitHub Actions scheduled SEC scans, historical quarterly comparisons, CSV export, and manager search. **No paid hosting or database required** for a modest personal watchlist. Starts with Gavin Baker's Atreides Management and five other managers.

## Deploy on GitHub (about 10 minutes)

1. Create a GitHub repository with the **contents** of this folder at its root, on the `main` branch. A **public** repository is the simplest route for free GitHub Pages. The JSON holdings are public in a public repository.
2. Under **Settings → Secrets and variables → Actions**, add a repository secret named `SEC_USER_AGENT`, with a value like `13F Intelligence Your Name your-real-email@example.com`. Use your real contact information. Never put it in a committed file.
3. Under **Settings → Actions → General → Workflow permissions**, select **Read and write permissions** for the workflow's ability to commit updated data. Organization restrictions may override this.
4. Under **Settings → Pages → Build and deployment**, select **GitHub Actions** as the source.
5. Under **Actions → Scan SEC 13F filings → Run workflow**, run the initial scan. The workflow saves JSON into `docs/data/` and commits it. A subsequent push triggers **Publish dashboard**. You can also manually run **Publish dashboard**.
6. Open your Pages URL shown under **Settings → Pages** or in the deployment job. No custom domain is necessary.

The initial scan needs network access to the SEC and may take several minutes. If the SEC blocks GitHub-hosted runners, the job will fail with errors; see fallback below.

## Scheduled scans

`.github/workflows/scan.yml` checks every day at **12:00 UTC** (7 AM EST, 8 AM EDT). GitHub's cron is UTC and can be delayed or occasionally skipped. To scan at a consistent 7 AM Eastern time year-round, use a timezone-aware external scheduler or adjust the UTC cron seasonally. GitHub can disable scheduled workflows in inactive public repositories; review the Actions tab occasionally.

Each scan checks SEC submissions, downloads new filing XML tables, and retains the most recent **8 reporting periods** per manager. Unchanged holdings are reused from the JSON snapshot and no new commit is made unless a filing changes. Newly detected SEC accession numbers replace the stored quarter where appropriate. On update, the scan commits `docs/data/*.json`, which triggers Pages deployment. The dashboard is static: the Refresh button reloads the last *stored* scan, not a live SEC request. The UI calculates New/Increased/Reduced/Exited by comparing shares in adjacent quarters.

## Add managers

Edit `managers.json` with `name`, `manager`, and 10-digit SEC `cik`, commit, then manually run **Scan SEC 13F filings**. Search searches the **tracked manager list**, not the entire SEC directory. The original Python proxy server remains available for experimental live CIK lookup, but the static Pages app only displays managers with scanned JSON.

## Local preview

After an initial scan has generated data:

```bash
python3 -m http.server 8765 --directory docs
```

Open http://localhost:8765. You can also use `python3 server.py` for the original live-fetch backend; it serves the original `static/` dashboard and does **not** use the scheduled JSON data.

## Optional persistent database and alerts

This starter edition stores up to 8 quarters of holdings as committed JSON in GitHub. **Supabase is not required**. For more managers or longer retention, a database is a useful future upgrade. Email/push notifications and AI-generated summaries are **not yet implemented**. GitHub Actions provides scan failure notifications according to your GitHub notification settings, but not position-change alerts.

## Important limitations

- 13F filings are delayed snapshots, not live trades. They omit shorts and many assets. The app does not infer purchases or sales from market-value changes; it compares reported share counts.
- 13F-HR/A amendments can be restatements or supplemental filings. This implementation picks the latest filing for a reporting period and **does not merge supplemental amendments**, so amended quarters may be incomplete.
- SEC XML values are reported in thousands of dollars. The parser multiplies by 1,000.
- XML extraction can fail on older or nonstandard filings; a failed manager scan preserves its previously committed JSON.
- Free-tier availability and GitHub Pages eligibility depend on current provider terms and repository visibility. Never commit credentials or sensitive personal data.
- `MAX_QUARTERS` defaults to 8. When the oldest quarter rolls off, the oldest visible quarter won't have a prior-quarter comparison.

## Files

- `scripts/scan.py`: scheduled data collection
- `.github/workflows/scan.yml`: SEC scanner and Git commit
- `.github/workflows/pages.yml`: static dashboard deployment
- `docs/index.html`: dashboard
- `docs/data/`: generated snapshots
- `managers.json`: tracked manager list
- `server.py`, `static/index.html`: original live local app
