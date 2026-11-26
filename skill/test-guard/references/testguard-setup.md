# Setting up testguard

`tools/testguard/testguard.py` (installed by `install.sh`), Python 3.11+, standard library only.

```toml
# testing/testguard.toml — paths relative to root
root = ".."

[rules]
files = ["docs/prd/rules.md"]                  # where rules are defined
id_pattern = 'BR-[A-Z]+\d+[a-z]?'              # required; project-specific
# definition_pattern defaults to a Markdown table row: | <ID> | <title> |
allowlist = "testing/uncovered-rules.allowlist"

[tests]
include = ["**/src/test/**", "tests/**", "scripts/*e2e*.sh", "web/tests/**"]
exclude = ["**/fixtures/large/**"]
kinds = ["happy", "boundary", "over", "invalid", "auth", "concurrency", "idempotency", "time", "failure"]
# Extra citation styles, e.g. test names like brP3_rejectsOverCapacity:
[[tests.citation]]
pattern = '\bbr([A-Z]+)(\d+[a-z]?)_'
template = "BR-{1}{2}"

[tests.require_kinds]                          # optional, raise per rule family over time
"BR-P*" = ["happy", "boundary", "over"]

[evidence]                                     # optional: JUnit XML written by the test run
junit = ["**/target/surefire-reports/TEST-*.xml", "web/reports/junit.xml"]
min_tests = 150                                # catches "the task ran nothing"

[docs]
spec = ["docs/testing/test-spec.md"]           # backticked paths in these files must exist
matrix = "docs/testing/coverage-matrix.md"
path_prefixes = ["docs/", "scripts/", "src/", "tools/"]   # only check paths that start like this
```

Commands:

```sh
python3 tools/testguard/testguard.py check  --config testing/testguard.toml   # CI, pre-push
python3 tools/testguard/testguard.py matrix --config testing/testguard.toml   # commit the result
python3 tools/testguard/testguard.py drift  --config testing/testguard.toml --json   # scheduled loop
python3 tools/testguard/testguard.py init   --config testing/testguard.toml --baseline
```

Run `check` after the test suite so the `evidence` section sees fresh reports. Allowlist lines:
`RULE-ID | reason | iteration that covers it`; an entry fails once the rule is covered (delete it) or removed.
