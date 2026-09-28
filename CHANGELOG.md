# Changelog

## 1.0.0 (2026-09-28)

- Initial public release: 7 auditors (JVG, IDA, SRA, SAL, FSA, LGA, SCI).
- All seven `verify.py` self-checks pass end-to-end.
- Local absolute paths in resource lookups parameterized via environment
  variables (`ZHENGMING_WS`, `ZHENGMING_HOME`) with `Path.home()` fallbacks.
