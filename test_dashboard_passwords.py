import hashlib
import importlib
import inspect
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from argon2 import PasswordHasher
from argon2.low_level import Type
from fastapi import HTTPException

from api import passwords
from api.security import AuthenticatedUser


class PasswordHelperTests(unittest.TestCase):
    def test_new_hash_uses_argon2id_format(self):
        result = passwords.hash_password("test-password")

        self.assertTrue(result.startswith("$argon2id$"))

    def test_same_password_produces_different_hashes(self):
        first_hash = passwords.hash_password("test-password")
        second_hash = passwords.hash_password("test-password")

        self.assertNotEqual(first_hash, second_hash)

    def test_argon2_password_verification(self):
        stored_hash = passwords.hash_password("correct-password")

        self.assertTrue(passwords.verify_password("correct-password", stored_hash))
        self.assertFalse(passwords.verify_password("wrong-password", stored_hash))

    def test_legacy_sha256_detection_and_verification(self):
        stored_hash = hashlib.sha256(b"legacy-password").hexdigest()

        self.assertTrue(passwords.is_legacy_sha256_hash(stored_hash))
        self.assertTrue(passwords.verify_password("legacy-password", stored_hash))
        self.assertFalse(passwords.verify_password("wrong-password", stored_hash))

    def test_non_hex_64_character_string_is_not_legacy(self):
        self.assertFalse(passwords.is_legacy_sha256_hash("z" * 64))

    def test_malformed_hash_is_rejected_safely(self):
        self.assertFalse(passwords.verify_password("test-password", "not-a-valid-hash"))
        self.assertFalse(passwords.password_needs_upgrade("not-a-valid-hash"))

    def test_legacy_hash_needs_upgrade(self):
        stored_hash = hashlib.sha256(b"legacy-password").hexdigest()

        self.assertTrue(passwords.password_needs_upgrade(stored_hash))

    def test_current_argon2_hash_does_not_need_upgrade(self):
        stored_hash = passwords.hash_password("test-password")

        self.assertFalse(passwords.password_needs_upgrade(stored_hash))


class PasswordRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cursor = MagicMock()
        cls.conn = MagicMock()
        fake_database = types.ModuleType("core.database")
        fake_database.cursor = cls.cursor
        fake_database.conn = cls.conn
        cls.modules_patcher = patch.dict(
            sys.modules,
            {"core.database": fake_database},
        )
        cls.modules_patcher.start()
        sys.modules.pop("api.auth", None)
        cls.auth = importlib.import_module("api.auth")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("api.auth", None)
        cls.modules_patcher.stop()

    def setUp(self):
        self.cursor.reset_mock()
        self.conn.reset_mock()
        self.conn.commit.side_effect = None
        self.token_patcher = patch.object(
            self.auth,
            "create_access_token",
            return_value="test-token",
        )
        self.create_access_token = self.token_patcher.start()

    def tearDown(self):
        self.token_patcher.stop()

    @staticmethod
    def _user(password):
        return types.SimpleNamespace(username="alice", password=password)

    @staticmethod
    def _admin():
        return AuthenticatedUser(user_id=1, username="admin", role="admin")

    def test_register_stores_argon2id_hash(self):
        self.cursor.fetchone.return_value = None

        self.auth.register(self._user("new-password"), self._admin())

        insert_call = self.cursor.execute.call_args_list[1]
        stored_hash = insert_call.args[1][1]
        self.assertTrue(stored_hash.startswith("$argon2id$"))
        self.assertTrue(passwords.verify_password("new-password", stored_hash))
        self.conn.commit.assert_called_once_with()

    def test_legacy_login_migrates_before_issuing_token(self):
        legacy_hash = hashlib.sha256(b"legacy-password").hexdigest()
        self.cursor.fetchone.return_value = {
            "id": 7,
            "username": "alice",
            "role": "user",
            "password": legacy_hash,
        }

        result = self.auth.login(self._user("legacy-password"))

        select_call, update_call = self.cursor.execute.call_args_list
        self.assertEqual(
            select_call.args,
            (
                "SELECT id, username, role, password FROM users WHERE username=%s",
                ("alice",),
            ),
        )
        self.assertEqual(
            update_call.args[0],
            "UPDATE users SET password=%s WHERE id=%s",
        )
        self.assertTrue(update_call.args[1][0].startswith("$argon2id$"))
        self.assertEqual(update_call.args[1][1], 7)
        self.conn.commit.assert_called_once_with()
        self.create_access_token.assert_called_once_with(
            user_id=7,
            username="alice",
            role="user",
        )
        self.assertEqual(result["token"], "test-token")

    def test_wrong_legacy_password_has_no_side_effects(self):
        legacy_hash = hashlib.sha256(b"legacy-password").hexdigest()
        self.cursor.fetchone.return_value = {
            "id": 7,
            "username": "alice",
            "role": "user",
            "password": legacy_hash,
        }

        with self.assertRaises(HTTPException) as caught:
            self.auth.login(self._user("wrong-password"))

        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail, "Invalid username or password")
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.conn.commit.assert_not_called()
        self.create_access_token.assert_not_called()

    def test_current_argon2_login_does_not_migrate(self):
        stored_hash = passwords.hash_password("current-password")
        self.cursor.fetchone.return_value = {
            "id": 7,
            "username": "alice",
            "role": "user",
            "password": stored_hash,
        }

        self.auth.login(self._user("current-password"))

        self.assertEqual(self.cursor.execute.call_count, 1)
        self.conn.commit.assert_not_called()
        self.create_access_token.assert_called_once()

    def test_argon2_hash_needing_rehash_is_migrated(self):
        weak_hasher = PasswordHasher(
            time_cost=1,
            memory_cost=8192,
            parallelism=1,
            type=Type.ID,
        )
        stored_hash = weak_hasher.hash("rehash-password")
        self.cursor.fetchone.return_value = {
            "id": 7,
            "username": "alice",
            "role": "user",
            "password": stored_hash,
        }

        self.auth.login(self._user("rehash-password"))

        self.assertEqual(self.cursor.execute.call_count, 2)
        upgraded_hash = self.cursor.execute.call_args.args[1][0]
        self.assertTrue(upgraded_hash.startswith("$argon2id$"))
        self.conn.commit.assert_called_once_with()
        self.create_access_token.assert_called_once()

    def test_unknown_user_is_rejected_without_side_effects(self):
        self.cursor.fetchone.return_value = None

        with self.assertRaises(HTTPException) as caught:
            self.auth.login(self._user("unknown-password"))

        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail, "Invalid username or password")
        self.conn.commit.assert_not_called()
        self.create_access_token.assert_not_called()

    def test_failed_migration_rolls_back_and_does_not_issue_token(self):
        legacy_hash = hashlib.sha256(b"legacy-password").hexdigest()
        self.cursor.fetchone.return_value = {
            "id": 7,
            "username": "alice",
            "role": "user",
            "password": legacy_hash,
        }
        self.conn.commit.side_effect = RuntimeError("database write failed")

        with self.assertRaises(RuntimeError):
            self.auth.login(self._user("legacy-password"))

        self.conn.rollback.assert_called_once_with()
        self.create_access_token.assert_not_called()

    def test_source_has_no_password_in_login_where_clause(self):
        source = inspect.getsource(self.auth)

        self.assertNotIn("WHERE username=%s AND password=%s", source)


if __name__ == "__main__":
    unittest.main()
