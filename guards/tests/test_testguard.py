import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testguard"))
import testguard  # noqa: E402

CONFIG = r"""
[rules]
files = ["docs/rules.md"]
id_pattern = 'BR-[A-Z]+\d+[a-z]?'
allowlist = "testing/uncovered-rules.allowlist"

[tests]
include = ["src/test/**", "tests/**"]
[[tests.citation]]
pattern = '\bbr([A-Z]+)(\d+[a-z]?)_'
template = "BR-{1}{2}"

[evidence]
junit = ["reports/*.xml"]
min_tests = 2

[docs]
spec = ["docs/testing/test-spec.md"]
matrix = "docs/testing/coverage-matrix.md"
"""

RULES = """
| ID | Rule | Source |
|---|---|---|
| BR-P3 | A parcel belongs to at most one active task | R02 |
| BR-G5 | The business day is the station's local day | H07 |
| BR-X1 | Every change is audited | H14 |
"""

JUNIT_OK = '<testsuite name="s" tests="3" failures="0" errors="0" skipped="0"/>'


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write("testguard.toml", CONFIG)
        self.write("docs/rules.md", RULES)
        self.write("reports/TEST-a.xml", JUNIT_OK)
        self.write("docs/testing/test-spec.md", "Run `src/test/` and `docs/rules.md`.\n")

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text))

    def cfg(self):
        return testguard.load_config(self.root / "testguard.toml")

    def errors(self):
        return testguard.check(self.cfg())[0]


ALL_COVERED = """
class PlanningTest {
    // BR-P3:boundary capacity exactly full
    void brP3_assignsUpToCapacity() {}
    void brG5_dayFollowsStationZone() {}  // BR-G5:time
    /* BR-X1 */ void auditsEveryChange() {}
}
"""


class TestguardTest(unittest.TestCase):
    def repo(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        return r

    def test_all_rules_cited_passes(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", ALL_COVERED)
        self.assertEqual([], r.errors())

    def test_rules_are_read_from_the_definition_table(self):
        r = self.repo()
        self.assertEqual(["BR-P3", "BR-G5", "BR-X1"], list(testguard.rules(r.cfg())))

    def test_an_uncovered_rule_fails_until_tested_or_allowlisted(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", "void brP3_x() {} void brG5_y() {}")
        errors = r.errors()
        self.assertEqual(1, len(errors), errors)
        self.assertIn("BR-X1", errors[0])
        r.write("testing/uncovered-rules.allowlist", "BR-X1 | audit is tested manually today | Q1\n")
        self.assertEqual([], r.errors())

    def test_name_based_citations_use_the_template(self):
        r = self.repo()
        r.write("docs/testing/test-spec.md", "Tests live in `tests/`.\n")
        r.write("tests/test_planning.py", "def test_x():  # brP3_ style is not python, but the pattern is configured\n    pass\nbrG5_ok = 1\nbrX1_ok = 1\nbrP3_ok = 1\n")
        self.assertEqual([], r.errors())

    def test_a_stale_allowlist_entry_fails_so_the_list_only_shrinks(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", ALL_COVERED)
        r.write("testing/uncovered-rules.allowlist", "BR-X1 | old | Q1\nBR-Z9 | gone | Q1\n")
        errors = r.errors()
        self.assertTrue(any("BR-X1 is covered now" in e for e in errors), errors)
        self.assertTrue(any("BR-Z9 is not a defined rule" in e for e in errors), errors)

    def test_a_citation_of_a_removed_rule_fails(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", ALL_COVERED + "\n// BR-P9 was split\n// UTF-8 is not a rule\n")
        errors = r.errors()
        self.assertEqual(1, len(errors), errors)
        self.assertIn("cites BR-P9", errors[0])

    def test_required_case_kinds_are_enforced(self):
        r = self.repo()
        r.write("testguard.toml", CONFIG + '\n[tests.require_kinds]\n"BR-P*" = ["happy", "boundary"]\n')
        r.write("src/test/PlanningTest.java", ALL_COVERED)
        errors = r.errors()
        self.assertTrue(any("BR-P3 lacks case kinds ['happy']" in e for e in errors), errors)

    def test_evidence_requires_reports_enough_tests_and_no_failures(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", ALL_COVERED)
        r.write("reports/TEST-a.xml", '<testsuite tests="1" failures="0" errors="0"/>')
        self.assertTrue(any("only 1 tests ran" in e for e in r.errors()))
        r.write("reports/TEST-a.xml", '<testsuites><testsuite tests="4" failures="1" errors="0"/></testsuites>')
        self.assertTrue(any("1 test(s) failed" in e for e in r.errors()))
        (r.root / "reports/TEST-a.xml").unlink()
        self.assertTrue(any("no test reports" in e for e in r.errors()))

    def test_a_spec_referencing_a_missing_path_fails(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", ALL_COVERED)
        r.write("docs/testing/test-spec.md", "Use `src/test/` and the `src/main/resources/application-memory.properties` profile.\n")
        errors = r.errors()
        self.assertTrue(any("application-memory.properties" in e for e in errors), errors)

    def test_matrix_and_drift_report_coverage_changes(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", ALL_COVERED)
        cfg = r.cfg()
        text = testguard.matrix(cfg)
        self.assertIn("Covered **3 / 3** rules", text)
        self.assertIn("| BR-P3 |", text)
        self.assertIn("boundary", text)
        cfg.matrix_file.parent.mkdir(parents=True, exist_ok=True)
        cfg.matrix_file.write_text(text)
        unchanged = testguard.drift(cfg)
        self.assertFalse(unchanged["matrix_outdated"])
        self.assertEqual([], unchanged["removed_rules"])  # the |---| separator row is not a rule
        r.write("docs/rules.md", RULES + "| BR-D4 | A failed parcel is retried once | H09 |\n")
        r.write("src/test/PlanningTest.java", "void brP3_x() {} void brG5_y() {}")
        d = testguard.drift(r.cfg())
        self.assertEqual(["BR-D4"], d["new_rules"])
        self.assertEqual(["BR-X1"], d["coverage_lost"])
        self.assertTrue(d["matrix_outdated"])

    def test_init_baseline_allowlists_uncovered_rules_with_placeholders(self):
        r = self.repo()
        r.write("src/test/PlanningTest.java", "void brP3_x() {}")
        testguard.init(r.cfg(), baseline=True)
        allow = (r.root / "testing/uncovered-rules.allowlist").read_text()
        self.assertIn("BR-G5 | TODO reason | TBD", allow)
        self.assertEqual([], r.errors())


if __name__ == "__main__":
    unittest.main()
