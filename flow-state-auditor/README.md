# FSA — 流态审计器 (Flow-State Auditor)

> ⚪ UNASSIGNED — 无正面授权记录，待人工拍板
> Zero external dependencies · offline · single-file CLI · Python 3.9+

## What it audits

Audits the state of a streaming/flowing output: what is asserted before it is known.

审流式输出在「还没想完就已经说出口」时留下的账。

## Usage

```bash
python fsa_cli.py --help
python fsa_cli.py selftest      # or equivalent self-check
python verify.py           # end-to-end reconciliation gate (R-BK2)
```

## Files

| File | Role |
|---|---|
| `build_html.py` | |
| `collect_corpus.py` | |
| `fsa_cli.py` | |
| `probe_stream_reality.py` | |
| `verify.py` | |

## Handbook (internal)

`~/.workbuddy/rules/突破件/突破-2026-09-27-流态审计器FSAv1.0.md`

## Provenance

Breakthrough artifact v1.0 · batch 2026-09-27 · produced via the seven-flow
breakthrough pipeline from a Douyin source. Score gate and reconciliation
anchors are recorded in the handbook.

> **Corpus note**: this copy ships code + self-produced fixtures only. Raw
> corpora (`_raw/`, `corpus/`, `_clones/`) are deliberately excluded — rerun
> the collector before `verify.py` if you need the end-to-end gate.
