# zhengming-auditors

Seven zero-dependency, single-file CLI auditors. Each one catches one class of
**silent failure** — the kind where a machine gets something wrong and reports
nothing: a stream cut short and called complete, a claim of learning that was
never reconciled, an agent whose actions and words disagree.

Every item ships with a `verify.py` self-check that runs the auditor against
its own fixtures; all seven pass end-to-end.

| Abbr | Auditor | What it catches |
|---|---|---|
| JVG | Jev Misuse Gate | A model-specific prohibition reused as a universal conclusion |
| IDA | Information Debt Auditor | Information dropped by compression and never read back, accruing as debt |
| SRA | Silence Reconciliation Auditor | Silences that should have happened but did not |
| SAL | Sandbox Action Ledger | Gap between what an agent did in its sandbox and what it said it did |
| FSA | Flow-State Auditor | A truncated stream judged complete because "the flow ended" |
| LGA | Life Guide Audit | Advice that its own reader cannot actually execute |
| SCI | Self-Claimed Inheritance Auditor | "I have learned X" claims with nothing behind them |

## Why

Most QA checks ask *did it crash?*. These auditors ask the other question:
**did it finish, and can you prove it?** Truncation is not an exception — it
arrives as a normal-looking end-of-stream with `err=None`. Silence is not an
error — it is the absence of an error message. That is exactly why ordinary
tooling misses them.

## Usage

Each directory is self-contained (see its README):

```bash
python flow-state-auditor/probe_stream_reality.py   # run one auditor's probe
python flow-state-auditor/verify.py                 # its self-check
```

Requirements: Python 3.10+. No third-party packages.

## License

MIT
