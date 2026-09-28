# SCI — 自述继承审计器 (Self-Claimed Inheritance Auditor)

> ⚪ UNASSIGNED — 无正面授权记录，待人工拍板
> Zero external dependencies · offline · single-file CLI · Python 3.9+

## What it audits

Audits whether "I have learned X" was ever reconciled with what was actually gained.

审「我学会了 X」这句自述，与真正获得了什么，是否有过对账。

## Usage

```bash
python sci_cli.py --help
python sci_cli.py selftest      # or equivalent self-check
python verify.py           # end-to-end reconciliation gate (R-BK2)
```

## Files

| File | Role |
|---|---|
| `build_html.py` | |
| `collect_corpus.py` | |
| `probe_claimed_inheritance.py` | |
| `sci_cli.py` | |
| `verify.py` | |

## Handbook (internal)

`~/.workbuddy/rules/突破件/突破-2026-09-27-自述继承审计器SCIv1.0.md`

## Provenance

Breakthrough artifact v1.0 · batch 2026-09-27 · produced via the seven-flow
breakthrough pipeline from a Douyin source. Score gate and reconciliation
anchors are recorded in the handbook.

> **Corpus note**: this copy ships code + self-produced fixtures only. Raw
> corpora (`_raw/`, `corpus/`, `_clones/`) are deliberately excluded — rerun
> the collector before `verify.py` if you need the end-to-end gate.
