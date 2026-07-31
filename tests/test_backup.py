from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
import uuid
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.system.backup import (
    _copy_data_folder,
    create_backup,
    restore_backup,
    validate_backup,
)


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
        notebook_dir = self.data_dir / "notebook" / "engagement-1" / "note-1"
        notebook_dir.mkdir(parents=True)
        (notebook_dir / "response.http").write_text("HTTP/1.1 403", encoding="utf-8")
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
            self.assertIn("data/notebook/engagement-1/note-1/response.http", members)
            self.assertIn("data/templates/template-1/logo.png", members)
            self.assertIn("data/jobs/job-1/output.txt", members)
            self.assertNotIn(".env", members)
            self.assertNotIn(".secret_key", members)

    def test_backup_skips_a_runtime_file_that_vanishes_during_copy(self):
        source = self.data_dir / "reports"
        destination = self.root / "snapshot" / "reports"
        source.mkdir()
        stable = source / "stable.docx"
        volatile = source / "volatile.tmp"
        stable.write_bytes(b"stable")
        volatile.write_bytes(b"temporary")
        original_copy = shutil.copy2

        def copy_with_rotation(source_file, destination_file):
            if Path(source_file).name == volatile.name:
                volatile.unlink()
                raise FileNotFoundError(volatile)
            return original_copy(source_file, destination_file)

        with patch("app.system.backup.shutil.copy2", side_effect=copy_with_rotation):
            copied = _copy_data_folder(source, destination)

        self.assertEqual([destination / stable.name], copied)
        self.assertEqual(b"stable", (destination / stable.name).read_bytes())
        self.assertFalse((destination / volatile.name).exists())

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
        notebook_file = self.data_dir / "notebook" / "engagement-1" / "note-1" / "response.http"
        notebook_file.write_text("HTTP/1.1 200", encoding="utf-8")
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
        self.assertEqual(notebook_file.read_text(encoding="utf-8"), "HTTP/1.1 403")
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

        alias_backup = self.root / "path-alias.zip"
        with ZipFile(alias_backup, "w") as archive:
            archive.writestr("database/breachwright.db", b"one")
            archive.writestr("DATABASE/BREACHWRIGHT.DB", b"two")
        with self.assertRaisesRegex(ValueError, "Duplicate backup path"):
            validate_backup(alias_backup)

        alternate_stream_backup = self.root / "alternate-stream.zip"
        with ZipFile(alternate_stream_backup, "w") as archive:
            archive.writestr("data/evidence/proof.txt:payload", b"unsafe")
        with self.assertRaisesRegex(ValueError, "Unsafe backup path"):
            validate_backup(alternate_stream_backup)

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

    def test_rejects_unreadable_archives_and_missing_display_metadata(self):
        unreadable_backup = self.root / "not-a-backup.zip"
        unreadable_backup.write_text("plain text", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "archive cannot be read"):
            validate_backup(unreadable_backup)

        missing_backup = self.root / "missing.zip"
        with self.assertRaisesRegex(ValueError, "archive cannot be read"):
            validate_backup(missing_backup)

        database_content = b"not-a-real-database"
        incomplete_backup = self.root / "incomplete-metadata.zip"
        with ZipFile(incomplete_backup, "w") as archive:
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
                                "sha256": hashlib.sha256(database_content).hexdigest(),
                            }
                        },
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "manifest metadata is invalid"):
            validate_backup(incomplete_backup)


if __name__ == "__main__":
    unittest.main()
