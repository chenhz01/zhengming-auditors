# SRA — 沉默对账器 (Silence Reconciliation Auditor)

> ⚪ UNASSIGNED — 无正面授权记录，待人工拍板
> Zero external dependencies · offline · single-file CLI · Python 3.9+

## What it audits

Audits the silence that should not have happened.

审「本该发生却没有发生的沉默」。

## Usage

```bash
python sra_cli.py --help
python sra_cli.py selftest      # or equivalent self-check
python verify.py           # end-to-end reconciliation gate (R-BK2)
```

## Files

| File | Role |
|---|---|
| `build_html.py` | |
| `collect_corpus.py` | |
| `probe_silence_reality.py` | |
| `sra_cli.py` | |
| `verify.py` | |

## Handbook (internal)

`~/.workbuddy/rules/突破件/突破-2026-09-27-沉默对账器SRAv1.0.md`

## Provenance

Breakthrough artifact v1.0 · batch 2026-09-27 · produced via the seven-flow
breakthrough pipeline from a Douyin source. Score gate and reconciliation
anchors are recorded in the handbook.

> **Corpus note**: this copy ships code + self-produced fixtures only. Raw
> corpora (`_raw/`, `corpus/`, `_clones/`) are deliberately excluded — rerun
> the collector before `verify.py` if you need the end-to-end gate.
