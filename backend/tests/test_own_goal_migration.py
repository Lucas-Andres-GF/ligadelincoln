"""Static contract tests for the own-goal lineup migration."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "20260928_add_own_goals_to_lineups.sql"
)


def migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def normalized_sql() -> str:
    without_line_comments = re.sub(r"--[^\n]*", "", migration_sql())
    return re.sub(r"\s+", " ", without_line_comments).strip()


class OwnGoalMigrationContractTests(unittest.TestCase):
    def test_migration_is_wrapped_in_one_explicit_transaction(self) -> None:
        sql = normalized_sql()

        self.assertRegex(sql, re.compile(r"^BEGIN\s*;", re.IGNORECASE))
        self.assertRegex(sql, re.compile(r"COMMIT\s*;$", re.IGNORECASE))
        self.assertEqual(len(re.findall(r"\bBEGIN\s*;", sql, re.IGNORECASE)), 1)
        self.assertEqual(len(re.findall(r"\bCOMMIT\s*;", sql, re.IGNORECASE)), 1)

    def test_column_has_the_exact_additive_contract(self) -> None:
        sql = normalized_sql()

        declaration = re.compile(
            r"ALTER TABLE public\.alineaciones "
            r"ADD COLUMN IF NOT EXISTS goles_en_contra "
            r"integer NOT NULL DEFAULT 0\s*;",
            re.IGNORECASE,
        )
        self.assertEqual(len(declaration.findall(sql)), 1)
        self.assertNotRegex(
            sql,
            re.compile(r"ALTER\s+COLUMN\s+goles_en_contra", re.IGNORECASE),
        )

    def test_non_negative_constraint_creation_is_guarded_and_rerunnable(self) -> None:
        sql = normalized_sql()
        constraint_name = "alineaciones_goles_en_contra_non_negative"

        self.assertRegex(
            sql,
            re.compile(
                rf"IF NOT EXISTS\s*\(.*"
                rf"FROM pg_constraint.*"
                rf"conname\s*=\s*'{constraint_name}'.*"
                r"conrelid\s*=\s*'public\.alineaciones'::regclass.*"
                r"\)\s*THEN",
                re.IGNORECASE,
            ),
        )
        self.assertEqual(
            len(
                re.findall(
                    rf"ADD CONSTRAINT {constraint_name} "
                    r"CHECK\s*\(\s*goles_en_contra\s*>=\s*0\s*\)",
                    sql,
                    re.IGNORECASE,
                )
            ),
            1,
        )

    def test_migration_does_not_modify_data_or_security_configuration(self) -> None:
        sql = migration_sql()
        forbidden = (
            r"\bUPDATE\b",
            r"\bDELETE\s+FROM\b",
            r"\bTRUNCATE\b",
            r"\bDROP\b",
            r"\bGRANT\b",
            r"\bREVOKE\b",
            r"\bOWNER\s+TO\b",
            r"\b(?:ENABLE|DISABLE|FORCE|NO\s+FORCE)\s+ROW\s+LEVEL\s+SECURITY\b",
            r"\b(?:CREATE|ALTER|DROP)\s+POLICY\b",
        )

        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(sql, re.compile(pattern, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
