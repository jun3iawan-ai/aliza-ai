import ast
import os
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api import security


VALID_SECRET = "s" * security.JWT_MIN_SECRET_LENGTH
OTHER_VALID_SECRET = "t" * security.JWT_MIN_SECRET_LENGTH


class DashboardSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_missing_secret_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                security.validate_jwt_configuration()

    def test_empty_secret_is_rejected(self):
        with patch.dict(os.environ, {security.JWT_SECRET_ENV_VAR: "   "}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                security.validate_jwt_configuration()

    def test_short_secret_is_rejected(self):
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: "too-short"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "at least 32"):
                security.validate_jwt_configuration()

    def test_31_character_secret_with_whitespace_is_rejected(self):
        padded_short_secret = f"  {'s' * 31}\t\n"
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: padded_short_secret},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "at least 32"):
                security.validate_jwt_configuration()

    def test_edge_whitespace_is_normalized_for_token_operations(self):
        padded_secret = f" \t{VALID_SECRET}\n "
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: padded_secret},
            clear=True,
        ):
            self.assertEqual(security.get_jwt_secret(), VALID_SECRET)
            token = security.create_access_token(
                user_id=7,
                username="alice",
                role="user",
            )

        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: VALID_SECRET},
            clear=True,
        ):
            identity = security.decode_access_token(token)

        self.assertEqual(identity.user_id, 7)

    def test_valid_token_can_be_decoded(self):
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: VALID_SECRET},
            clear=True,
        ):
            token = security.create_access_token(
                user_id=7,
                username="alice",
                role="admin",
            )
            identity = security.decode_access_token(token)

        self.assertEqual(identity.user_id, 7)
        self.assertEqual(identity.username, "alice")
        self.assertEqual(identity.role, "admin")

    def test_expired_token_is_rejected(self):
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: VALID_SECRET},
            clear=True,
        ):
            token = security.create_access_token(
                user_id=7,
                username="alice",
                role="user",
                expires_delta=timedelta(seconds=-1),
            )
            with self.assertRaises(HTTPException) as caught:
                security.decode_access_token(token)

        self._assert_unauthorized(caught.exception)

    def test_wrong_signature_is_rejected(self):
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: VALID_SECRET},
            clear=True,
        ):
            token = security.create_access_token(
                user_id=7,
                username="alice",
                role="user",
            )

        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: OTHER_VALID_SECRET},
            clear=True,
        ):
            with self.assertRaises(HTTPException) as caught:
                security.decode_access_token(token)

        self._assert_unauthorized(caught.exception)

    def test_malformed_token_is_rejected(self):
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: VALID_SECRET},
            clear=True,
        ):
            with self.assertRaises(HTTPException) as caught:
                security.decode_access_token("not-a-jwt")

        self._assert_unauthorized(caught.exception)

    async def test_missing_bearer_token_returns_401(self):
        with self.assertRaises(HTTPException) as caught:
            await security.get_current_user(None)

        self._assert_unauthorized(caught.exception)

    async def test_user_role_is_rejected_by_require_admin(self):
        identity = security.AuthenticatedUser(
            user_id=7,
            username="alice",
            role="user",
        )

        with self.assertRaises(HTTPException) as caught:
            await security.require_admin(identity)

        self.assertEqual(caught.exception.status_code, 403)

    async def test_admin_role_is_accepted(self):
        identity = security.AuthenticatedUser(
            user_id=7,
            username="alice",
            role="admin",
        )

        result = await security.require_admin(identity)

        self.assertIs(result, identity)

    async def test_bearer_credentials_are_decoded(self):
        with patch.dict(
            os.environ,
            {security.JWT_SECRET_ENV_VAR: VALID_SECRET},
            clear=True,
        ):
            token = security.create_access_token(
                user_id=7,
                username="alice",
                role="user",
            )
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=token,
            )
            identity = await security.get_current_user(credentials)

        self.assertEqual(identity.user_id, 7)

    def test_source_has_no_environment_fallback_secret(self):
        for relative_path in ("api/security.py", "api/auth.py"):
            tree = ast.parse(Path(relative_path).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "getenv":
                    continue
                self.assertLessEqual(
                    len(node.args),
                    1,
                    f"Environment fallback found in {relative_path}:{node.lineno}",
                )

    def _assert_unauthorized(self, exc: HTTPException):
        self.assertEqual(exc.status_code, 401)
        self.assertEqual(exc.headers, {"WWW-Authenticate": "Bearer"})


if __name__ == "__main__":
    unittest.main()
