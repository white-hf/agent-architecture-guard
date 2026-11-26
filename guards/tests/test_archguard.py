import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "archguard"))
import archguard  # noqa: E402

CONFIG = """
[sources]
include = ["src/**/*.java", "src/**/*.py"]
data_access_pattern = "/persistence/"
[[domains.rule]]
pattern = "src/(?P<domain>[a-z]+)/"
[domains]
known = ["parcel", "dispatch", "casework"]
aliases = { planning = "dispatch" }
[schema]
migrations = ["db/*.sql"]
ownership = "architecture/table-ownership.properties"
[writes]
allowlist = "architecture/cross-domain-writes.allowlist"
"""


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write("archguard.toml", CONFIG)
        self.write("db/V1__init.sql", "CREATE TABLE parcel (id INT);\nCREATE TABLE driver_task (id INT);\n"
                                       "CREATE TABLE IF NOT EXISTS operational_case (id INT);\n")
        self.write("architecture/table-ownership.properties", "parcel=parcel\ndriver_task=dispatch\noperational_case=casework\n")

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text))

    def check(self):
        return archguard.check(archguard.load_config(self.root / "archguard.toml"))


JAVA_OWN = """
class TaskRepository {
    public void start(long id) { jdbc.update("UPDATE driver_task SET status='IN_PROGRESS' WHERE id=?", id); }
}
"""
JAVA_CROSS = """
class TaskRepository {
    public void markAssigned(long wave) {
        jdbc.update("UPDATE parcel SET status='ASSIGNED' WHERE id IN (SELECT parcel_id FROM x WHERE wave=?)", wave);
    }
}
"""


class ArchguardTest(unittest.TestCase):
    def repo(self):
        r = Repo()
        self.addCleanup(r.tmp.cleanup)
        return r

    def test_writes_to_own_tables_pass(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", JAVA_OWN)
        self.assertEqual([], r.check())

    def test_a_cross_domain_write_fails_until_allowlisted_with_a_reason(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", JAVA_CROSS)
        errors = r.check()
        self.assertEqual(1, len(errors))
        self.assertIn("dispatch writes 'parcel'", errors[0])
        self.assertIn("TaskRepository#markAssigned", errors[0])
        r.write("architecture/cross-domain-writes.allowlist",
                "dispatch | TaskRepository#markAssigned | parcel | publish marks parcels set-based | S5\n")
        self.assertEqual([], r.check())

    def test_aliases_map_a_package_to_its_domain(self):
        r = self.repo()
        r.write("src/planning/persistence/PlanRepository.java", JAVA_OWN)
        self.assertEqual([], r.check())

    def test_a_stale_allowlist_entry_fails_so_the_list_only_shrinks(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", JAVA_OWN)
        r.write("architecture/cross-domain-writes.allowlist", "dispatch | TaskRepository#gone | parcel | old | S5\n")
        errors = r.check()
        self.assertTrue(any("no longer occurs" in e for e in errors), errors)

    def test_an_entry_without_reason_fails(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", JAVA_CROSS)
        r.write("architecture/cross-domain-writes.allowlist", "dispatch | TaskRepository#markAssigned | parcel\n")
        self.assertTrue(any("needs a reason" in e for e in r.check()))

    def test_an_unowned_or_stale_table_and_an_unknown_domain_fail(self):
        r = self.repo()
        r.write("db/V2__more.sql", "CREATE TABLE scan_event (id INT);")
        r.write("architecture/table-ownership.properties",
                "parcel=parcel\ndriver_task=dispatch\noperational_case=billing\nghost=parcel\n")
        errors = r.check()
        self.assertTrue(any("'scan_event'" in e and "no owner" in e for e in errors), errors)
        self.assertTrue(any("'ghost'" in e and "no migration" in e for e in errors), errors)
        self.assertTrue(any("unknown domain 'billing'" in e for e in errors), errors)

    def test_dropped_and_renamed_tables_follow_the_migrations(self):
        r = self.repo()
        r.write("db/V2__drop.sql", "DROP TABLE operational_case;\nRENAME TABLE driver_task TO task;")
        r.write("architecture/table-ownership.properties", "parcel=parcel\ntask=dispatch\n")
        self.assertEqual([], r.check())

    def test_upsert_columns_comments_and_code_outside_data_access_are_ignored(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", """
        class TaskRepository {
            // UPDATE parcel SET x=1   (comment, ignored)
            public void upsert() { jdbc.update("INSERT INTO driver_task(id) VALUES (1) ON DUPLICATE KEY UPDATE parcel=1"); }
        }
        """)
        r.write("src/dispatch/application/Service.java", 'class S { void f() { jdbc.update("UPDATE parcel SET a=1"); } }')
        self.assertEqual([], r.check())

    def test_entities_mapping_another_domains_table_are_writes(self):
        r = self.repo()
        r.write("src/casework/persistence/ParcelView.java", '@Entity\n@Table(name = "parcel")\nclass ParcelView {}')
        errors = r.check()
        self.assertTrue(any("ParcelView#@entity" in e for e in errors), errors)

    def test_python_functions_are_located(self):
        r = self.repo()
        r.write("src/casework/persistence/repo.py", 'def close_task(db):\n    db.execute("UPDATE driver_task SET s=1")\n')
        errors = r.check()
        self.assertTrue(any("repo#close_task" in e for e in errors), errors)

    def test_measure_reports_baseline_numbers(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", JAVA_CROSS)
        r.write("src/dispatch/application/Service.java", 'class S { String q = "SELECT * FROM parcel"; String m = "Select a station first"; }')
        m = archguard.measure(archguard.load_config(r.root / "archguard.toml"))
        self.assertEqual(3, m["tables"])
        self.assertEqual(1, m["cross_domain_writes"])
        self.assertEqual(1, m["sql_literals_outside_data_access"])

    def test_init_baseline_writes_placeholders(self):
        r = self.repo()
        r.write("src/dispatch/persistence/TaskRepository.java", JAVA_CROSS)
        archguard.init(archguard.load_config(r.root / "archguard.toml"), baseline=True)
        allow = (r.root / "architecture/cross-domain-writes.allowlist").read_text()
        self.assertIn("dispatch | TaskRepository#markAssigned | parcel | TODO reason | TBD", allow)
        self.assertEqual([], r.check())  # placeholders warn, they do not fail


if __name__ == "__main__":
    unittest.main()
