"""Static contracts for the production RLS/ACL SQL artifacts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SQL_DIR = BACKEND_DIR / "sql"
CANONICAL_SQL = SQL_DIR / "rls_public_read_admin_write.sql"
MIGRATION_SQL = SQL_DIR / "rls_acl_hardening_v2.sql"
ROLLBACK_SQL = SQL_DIR / "rls_acl_hardening_v2_rollback.sql"
OPERATIONS_DOC = BACKEND_DIR / "README_OPERACIONES.md"

APPLICATION_TABLES = {
    "alineaciones",
    "categorias",
    "clubes",
    "fechas",
    "goleadores",
    "goleadores_partido",
    "jugadores",
    "palmares",
    "participaciones",
    "partidos",
    "posiciones",
    "sanciones",
    "torneos",
}
ADMIN_EMAIL = "gallardolucas003@gmail.com"


def normalized(path: Path) -> str:
    """Return lowercase SQL with comments removed and whitespace collapsed."""
    text = path.read_text(encoding="utf-8").lower()
    text = re.sub(r"--[^\n]*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def assert_pattern(test: unittest.TestCase, text: str, pattern: str) -> None:
    test.assertRegex(text, re.compile(pattern, re.IGNORECASE))


def assert_supabase_default_acl_guard(
    test: unittest.TestCase, path: Path, expected_statements: tuple[str, ...]
) -> None:
    """Require fixed supabase_admin SQL inside one membership-gated DO block."""
    sql = normalized(path)
    blocks = list(re.finditer(r"do\s+\$\$(?P<body>.*?)end\s+\$\$\s*;", sql))
    guarded = [
        block
        for block in blocks
        if "supabase_admin" in block.group("body")
        and "pg_has_role" in block.group("body")
    ]
    test.assertEqual(len(guarded), 1, f"missing unique supabase_admin guard in {path}")

    guard = guarded[0]
    body = guard.group("body")
    assert_pattern(
        test,
        body,
        r"if pg_catalog\.pg_has_role\(current_user\s*,\s*'supabase_admin'\s*,\s*'member'\) then",
    )
    assert_pattern(
        test,
        body,
        r"else\s+raise (?:warning|notice)\s+'[^']*supabase_admin[^']*'[^;]*;\s+end if\s*;",
    )
    test.assertNotIn("format(", body, "guarded SQL must not interpolate identifiers")

    for statement in expected_statements:
        test.assertIn(
            f"execute '{statement}';",
            body,
            f"missing fixed guarded statement in {path}: {statement}",
        )

    outside_guard = sql[: guard.start()] + sql[guard.end() :]
    test.assertNotRegex(
        outside_guard,
        r"alter default privileges for role supabase_admin",
        f"unconditional supabase_admin default ACL statement in {path}",
    )
    test.assertEqual(
        body.count("alter default privileges for role supabase_admin"),
        len(expected_statements),
        f"unexpected supabase_admin default ACL statement in {path}",
    )


class HardeningSqlContractTests(unittest.TestCase):
    def assert_acl_hardening_contract(self, path: Path) -> None:
        sql = normalized(path)
        self.assertTrue(sql.startswith("begin;"), path)
        self.assertTrue(sql.endswith("commit;"), path)

        table_list = r"(?P<tables>(?:public\.[a-z_]+\s*,?\s*)+)"
        revoke = re.search(
            rf"revoke all privileges on table {table_list} from public\s*,\s*anon\s*,\s*authenticated\s*;",
            sql,
        )
        self.assertIsNotNone(revoke, f"missing direct table privilege reset in {path}")
        revoked_tables = set(re.findall(r"public\.([a-z_]+)", revoke.group("tables")))
        self.assertEqual(revoked_tables, APPLICATION_TABLES)

        for privileges, roles in (
            ("select", "anon, authenticated"),
            ("insert, update, delete", "authenticated"),
        ):
            pattern = (
                rf"grant {re.escape(privileges)} on table {table_list} "
                rf"to {re.escape(roles)}\s*;"
            )
            grant = re.search(pattern, sql)
            self.assertIsNotNone(grant, f"missing {privileges} grant in {path}")
            granted_tables = set(
                re.findall(r"public\.([a-z_]+)", grant.group("tables"))
            )
            self.assertEqual(granted_tables, APPLICATION_TABLES)

        self.assertNotRegex(
            sql,
            r"grant\s+(?:all(?: privileges)?|truncate|trigger|references|maintain)\s+on table",
        )
        assert_pattern(
            self,
            sql,
            r"revoke all privileges on all sequences in schema public from public\s*,\s*anon\s*,\s*authenticated\s*;",
        )
        assert_pattern(
            self,
            sql,
            r"grant usage on all sequences in schema public to authenticated\s*;",
        )
        self.assertNotRegex(sql, r"grant [^;]+ on all sequences[^;]+to (?:public|anon)")

        function = re.search(
            r"create or replace function public\.is_liga_admin\(\)(?P<body>.*?)\$\$\s*;",
            sql,
        )
        self.assertIsNotNone(function, f"missing admin function in {path}")
        for attribute in (r"\bstable\b", r"\bsecurity invoker\b", r"set search_path\s*=\s*''"):
            self.assertRegex(function.group("body"), attribute)
        self.assertEqual(
            re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", function.group("body")),
            [ADMIN_EMAIL],
        )
        assert_pattern(
            self,
            sql,
            r"revoke all privileges on function public\.is_liga_admin\(\) from public\s*,\s*anon\s*,\s*authenticated\s*;",
        )
        assert_pattern(
            self,
            sql,
            r"grant execute on function public\.is_liga_admin\(\) to authenticated\s*;",
        )

        for object_type in ("tables", "sequences", "functions"):
            assert_pattern(
                self,
                sql,
                r"alter default privileges for role postgres in schema public "
                rf"revoke all privileges on {object_type} from public\s*,\s*anon\s*,\s*authenticated\s*;",
            )

        for protected_role in ("service_role", "postgres", "supabase_admin"):
            self.assertNotRegex(sql, rf"revoke [^;]+ from [^;]*\b{protected_role}\b")

    def test_one_time_migration_has_complete_acl_contract(self) -> None:
        self.assert_acl_hardening_contract(MIGRATION_SQL)

    def test_canonical_hardening_has_same_complete_acl_contract(self) -> None:
        self.assert_acl_hardening_contract(CANONICAL_SQL)

    def test_acl_migration_does_not_change_policies_rls_or_data(self) -> None:
        sql = normalized(MIGRATION_SQL)
        forbidden = (
            r"\bcreate policy\b",
            r"\bdrop policy\b",
            r"\brow level security\b",
            r"\binsert into\b",
            r"\bupdate public\.",
            r"\bdelete from\b",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(sql, pattern)

    def test_supabase_admin_defaults_are_membership_guarded(self) -> None:
        expected = tuple(
            "alter default privileges for role supabase_admin in schema public "
            f"revoke all privileges on {object_type} from public, anon, authenticated"
            for object_type in ("tables", "sequences", "functions")
        )
        for path in (CANONICAL_SQL, MIGRATION_SQL):
            with self.subTest(path=path):
                assert_supabase_default_acl_guard(self, path, expected)


class RollbackSqlContractTests(unittest.TestCase):
    def test_rollback_is_transactional_scoped_and_prominently_dangerous(self) -> None:
        raw = ROLLBACK_SQL.read_text(encoding="utf-8").lower()
        sql = normalized(ROLLBACK_SQL)
        self.assertTrue(sql.startswith("begin;"))
        self.assertTrue(sql.endswith("commit;"))
        self.assertIn("danger", raw)
        self.assertIn("emergency", raw)
        self.assertIn("weakens", raw)

        table_list = r"(?P<tables>(?:public\.[a-z_]+\s*,?\s*)+)"
        grant = re.search(
            rf"grant all privileges on table {table_list} to anon\s*,\s*authenticated\s*;",
            sql,
        )
        self.assertIsNotNone(grant)
        self.assertEqual(
            set(re.findall(r"public\.([a-z_]+)", grant.group("tables"))),
            APPLICATION_TABLES,
        )
        self.assertNotRegex(sql, r"grant [^;]+ on table [^;]+ to [^;]*\bpublic\b")
        self.assertRegex(sql, r"grant all privileges on all sequences in schema public")
        self.assertRegex(sql, r"grant execute on function public\.is_liga_admin\(\)")
        for object_type in ("tables", "sequences", "functions"):
            self.assertRegex(
                sql,
                r"alter default privileges for role postgres in schema public "
                rf"grant .* on {object_type}",
            )

        expected = (
            "alter default privileges for role supabase_admin in schema public "
            "grant all privileges on tables to anon, authenticated",
            "alter default privileges for role supabase_admin in schema public "
            "grant all privileges on sequences to anon, authenticated",
            "alter default privileges for role supabase_admin in schema public "
            "grant execute on functions to public, anon, authenticated",
        )
        assert_supabase_default_acl_guard(self, ROLLBACK_SQL, expected)

        for forbidden in (
            r"\bcreate policy\b",
            r"\bdrop policy\b",
            r"\brow level security\b",
            r"\binsert into\b",
            r"\bupdate public\.",
            r"\bdelete from\b",
        ):
            self.assertNotRegex(sql, forbidden)


class OperationsDocumentationContractTests(unittest.TestCase):
    def test_acl_runbook_documents_apply_readback_rollback_and_auth_boundary(self) -> None:
        doc = re.sub(
            r"\s+", " ", OPERATIONS_DOC.read_text(encoding="utf-8").lower()
        )
        for expected in (
            "rls_acl_hardening_v2.sql",
            "rls_acl_hardening_v2_rollback.sql",
            "readback",
            "auth leaked password protection",
            "separado",
            "identidad sql configurada en mcp es de solo lectura",
            "manualmente en supabase sql editor",
            "drift residual de defaults de `supabase_admin`",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, doc)


if __name__ == "__main__":
    unittest.main()
