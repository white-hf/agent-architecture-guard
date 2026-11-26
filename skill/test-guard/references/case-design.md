# Case design: from a rule to cases to data

## 1. Case kinds

For every rule, decide which kinds apply. Write the decision in the matrix (a kind that does not apply is stated,
not silently missing).

| Kind | Question it answers | Typical data |
|---|---|---|
| `happy` | Does the rule hold for an ordinary, valid input? | One representative valid case |
| `boundary` | Does it hold exactly at the limit? | Capacity exactly full; deadline at the exact instant; one item; empty list where allowed |
| `over` | Is the limit enforced one step past it? | Capacity + 1; deadline + 1 s; amount one cent over |
| `invalid` | Are illegal inputs and illegal state transitions rejected with the documented error? | Wrong state, unknown id, missing mandatory field, malformed format |
| `auth` | Can only the right actor do it, in the right scope? | Another user's/tenant's/station's object; missing or expired credentials; insufficient role |
| `concurrency` | Is the rule kept when two actors act at once? | Two parallel claims of one item; optimistic-lock conflict; double approval |
| `idempotency` | Is a repeated request harmless? | Same request id twice; replayed webhook; retried upload |
| `time` | Does it hold across calendar/time-zone edges? | Local midnight, DST start/end, month/year end, leap day, per-zone business day |
| `failure` | What happens when a dependency fails mid-way? | Database error, remote 5xx/timeout, partial batch; assert all-or-nothing or the documented compensation |

Rules of thumb: a rule with a number in it (limits, deadlines, counts) needs `boundary` and `over`; a rule about who
may do something needs `auth`; a state machine needs `invalid` for every forbidden transition; anything that
accepts external input over a network needs `idempotency`; anything stored or displayed by date needs `time`.

## 2. Test data principles

1. **Each datum exists for a case.** If you cannot name the case a row serves, delete the row.
2. **Builders with valid defaults.** `aParcel().atStation(YVR).withPieces(2).arrived(1).build()` — the builder fills
   every other field with a valid value, so a test states only what the case is about, and a schema change is fixed
   in one place.
3. **Create, assert, clean up in the test.** Shared seeds: reference data only (users and roles, sites, catalogues,
   configuration). Never assert on rows you did not create.
4. **Look up by natural key.** `WHERE login='driver123'`, never `id = 101`.
5. **Unique per run.** Prefix keys with a run id, so parallel and repeated runs do not collide, and leftovers are
   recognisable. Flag test rows (`is_test`) when the schema supports it.
6. **Fixed time.** Inject a clock. Pick the instants the rule cares about. Compute expected instants with the
   platform's time-zone rules, not hand-written offsets.
7. **Realistic where it matters.** Geodata on land and inside the right area; real postal formats; names with
   non-ASCII characters; realistic volumes for performance cases.
8. **Separate data sets by purpose.** Unit fixtures (in code), integration seeds (reference data), end-to-end
   scenario data (created by the scenario), demo data (separate scripts, never in migrations), production data
   (never copied into tests).

## 3. Placing cases in layers

| Layer | Put here | Data |
|---|---|---|
| Unit (domain/core logic) | Most rule cases: every boundary, invalid transition, time edge | In-memory objects, fixed clock |
| Persistence / integration | Queries, constraints, locking, set-based updates, mapping/schema consistency | Throwaway database (container or in-memory with the same dialect), per-test data |
| API / contract | Status codes, error codes, auth scopes, request/response shapes, idempotency keys | Per-test data through the API or builders |
| Process smoke | Each deployable starts with all routes/components | Empty database |
| End-to-end | Each critical business path once or twice, across services | Fresh environment, reference seeds, scenario creates its own data |
| UI end-to-end | The few journeys a user must be able to complete | Same as end-to-end; stable selectors (roles/labels), not CSS paths |

The pyramid is a cost rule, not a dogma: push a case down to the cheapest layer that can observe the rule.

## 4. Matrix row format

The generated matrix (`testguard matrix`) lists rule → case kinds found → test files. When planning, write the
intended kinds next to the rule in the PR or iteration document:

```
BR-P3  a parcel belongs to at most one active task; capacity enforced
       need: happy, boundary, over, invalid, concurrency   (domain + persistence)
       have: happy, over                                     → add boundary, invalid, concurrency
```
