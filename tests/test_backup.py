from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
import uuid
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.system.backup import create_backup, restore_backup, validate_backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".breachwright-backup-test-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.data_dir = self.root / "data"
        self.data_dir.mkdir()
        self.database = self.data_dir / "breachwright.db"
        self.database_url = f"sqlite+aiosqlite:///{self.database.as_posix()}"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample VALUES ('original')")
            connection.commit()
        evidence_dir = self.data_dir / "evidence" / "finding-1"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "proof.txt").write_text("evidence", encoding="utf-8")
        template_dir = self.data_dir / "templates" / "template-1"
        template_dir.mkdir(parents=True)
        (template_dir / "logo.png").write_bytes(b"template-logo")
        job_dir = self.data_dir / "jobs" / "job-1"
        job_dir.mkdir(parents=True)
        (job_dir / "output.txt").write_text("tool output", encoding="utf-8")
        (self.data_dir / ".env").write_text("API_KEY=must-not-leak", encoding="utf-8")
        (self.data_dir / ".secret_key").write_text("secret", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_backup_is_verified_portable_and_excludes_secrets(self):
        backup = create_backup(
            str(self.data_dir),
            self.database_url,
            "test-version",
        )
        manifest = validate_backup(backup)

        self.assertEqual(manifest["app_version"], "test-version")
        with ZipFile(backup) as archive:
            members = archive.namelist()
            self.assertIn("database/breachwright.db", members)
            self.assertIn("data/evidence/finding-1/proof.txt", members)
            self.assertIn("data/templates/template-1/logo.png", members)
            self.assertIn("data/jobs/job-1/output.txt", members)
            self.assertNotIn(".env", members)
            self.assertNotIn(".secret_key", members)

    def test_restore_recovers_database_and_files_and_preserves_displaced_data(self):
        backup = create_backup(
            str(self.data_dir),
            self.database_url,
            "test-version",
        )
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE sample SET value = 'modified'")
            connection.commit()
        proof = self.data_dir / "evidence" / "finding-1" / "proof.txt"
        proof.write_text("modified evidence", encoding="utf-8")
        logo = self.data_dir / "templates" / "template-1" / "logo.png"
        logo.write_bytes(b"modified logo")
        job_output = self.data_dir / "jobs" / "job-1" / "output.txt"
        job_output.write_text("modified output", encoding="utf-8")

        safety_path = restore_backup(
            backup,
            str(self.data_dir),
            self.database_url,
        )

        with closing(sqlite3.connect(self.database)) as connection:
            value = connection.execute("SELECT value FROM sample").fetchone()[0]
        self.assertEqual(value, "original")
        self.assertEqual(proof.read_text(encoding="utf-8"), "evidence")
        self.assertEqual(logo.read_bytes(), b"template-logo")
        self.assertEqual(job_output.read_text(encoding="utf-8"), "tool output")
        self.assertTrue(
            (safety_path / "database" / "breachwright.db").is_file()
        )
        self.assertEqual(
            (safety_path / "evidence" / "finding-1" / "proof.txt").read_text(
                encoding="utf-8"
            ),
            "modified evidence",
        )
        self.assertEqual(
            (safety_path / "templates" / "template-1" / "logo.png").read_bytes(),
            b"modified logo",
        )
        self.assertEqual(
            (safety_path / "jobs" / "job-1" / "output.txt").read_text(
                encoding="utf-8"
            ),
            "modified output",
        )

    def test_rejects_traversal_and_checksum_tampering(self):
        traversal_backup = self.root / "traversal.zip"
        with ZipFile(traversal_backup, "w") as archive:
            archive.writestr("../outside.txt", b"unsafe")
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format_version": 1,
                        "database": "database/breachwright.db",
                        "files": {},
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "Unsafe backup path"):
            validate_backup(traversal_backup)

        tampered_backup = self.root / "tampered.zip"
        database_content = b"not-a-real-database"
        with ZipFile(tampered_backup, "w") as archive:
            archive.writestr("database/breachwright.db", database_content)
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format_version": 1,
                        "database": "database/breachwright.db",
                        "files": {
                            "database/breachwright.db": {
                                "size": len(database_content),
                                "sha256": hashlib.sha256(b"different").hexdigest(),
                            }
                        },
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            validate_backup(tampered_backup)

        unsigned_database_backup = self.root / "unsigned-database.zip"
        with ZipFile(unsigned_database_backup, "w") as archive:
            archive.writestr("database/breachwright.db", database_content)
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format_version": 1,
                        "database": "database/breachwright.db",
                        "files": {},
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "contents do not match"):
            validate_backup(unsigned_database_backup)

        unmanifested_file_backup = self.root / "unmanifested-file.zip"
        database_digest = hashlib.sha256(database_content).hexdigest()
        with ZipFile(unmanifested_file_backup, "w") as archive:
            archive.writestr("database/breachwright.db", database_content)
            archive.writestr("data/templates/template-1/logo.png", b"unsigned")
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format_version": 1,
                        "database": "database/breachwright.db",
                        "files": {
                            "database/breachwright.db": {
                                "size": len(database_content),
                                "sha256": database_digest,
                            }
                        },
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "contents do not match"):
            validate_backup(unmanifested_file_backup)


if __name__ == "__main__":
    unittest.main()
