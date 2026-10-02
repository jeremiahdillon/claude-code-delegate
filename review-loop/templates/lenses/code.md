---
categories: security, robustness, performance, testing, privacy
---
- Does it do what the intent says?
- Find inputs, states and orderings that break it: edge cases, error paths, concurrency, resume and retry, idempotency.
- Look for security and privacy leaks, and misuse of external APIs.
- Check whether the tests exercise the risky paths or only the happy path.
- Look for inconsistency between code, docs and config.
- **Reproduce bugs in a temporary copy wherever you can,** and cite what you ran.
