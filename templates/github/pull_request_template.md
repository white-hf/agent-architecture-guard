## What changes and why

## Architecture (required)
- Placement of every new class/file (domain / module / layer):
- Business rules implemented (IDs) and their tests:
- New escape-hatch SQL (class and category): none
- New tables registered in `architecture/table-ownership.properties`: n/a
- New cross-domain writes (must be none, or an approved allowlist entry with a reason): none

## Checks run
- [ ] full build with architecture tests
- [ ] `archguard check`
- [ ] end-to-end tests named in the spec
