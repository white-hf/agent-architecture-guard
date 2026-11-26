# <Project> architecture spec

> Status: PROPOSED | REVIEWED (date, reviewer). Applies to: <modules>. This document is binding for every coding
> agent; where it conflicts with habits or nearby code, this document wins.

## 1. Deployable units and modules
Table: unit/module, purpose, package root, may depend on. A diagram of the dependency direction.

## 2. Domains and ownership
Table: domain, module, responsibilities, owned tables, reference classes. Rule: one domain, one place.

## 3. Layers
Table: layer, responsibility, forbidden. Dependency rule. Where transactions start. Allowed extra package names
(e.g. `gateway`, `contract`) and forbidden ones.

## 4. Where new code goes (decision table)
Question → answer → location, covering: new rule, new use case, new endpoint, new query/report, new table, new
integration, a change that touches two domains.

## 5. Persistence
ORM scope, escape-hatch categories (each needs a comment), one entity per table, migration location, who runs
migrations, compatibility rule (expand then contract), locking and versioning.

## 6. Cross-domain collaboration
Same process: call the owner's application service in the caller's transaction. Other process: integration events
via the outbox. Read models: when joins across domains are allowed. Current exceptions: allowlist with reasons.

## 7. Cross-cutting rules
Time and time zones, identity and authorization source, idempotency, error codes, audit, logging of secrets.

## 8. Testing
Pyramid: domain unit tests (no DB, named after rule IDs) → persistence tests → web tests → end-to-end. Required
smoke tests per deployable.

## 9. Enforcement
Every MUST rule with its check (architecture test, guard test, lint, CI job). Baseline measurements. What a PR
must report.

## 10. Definition of done for a change
Build and architecture tests pass; listed E2E pass; placement and rule IDs stated; no new escape hatch or
cross-domain write without approval; docs updated in the languages the project uses.
