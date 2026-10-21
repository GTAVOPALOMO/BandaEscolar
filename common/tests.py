import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class DeploymentSettingsTests(SimpleTestCase):
    def vercel_environment(self):
        env = os.environ.copy()
        for name in (
            "DATABASE_URL", "DATABASE_SSL_REQUIRE", "SUPABASE_S3_ACCESS_KEY_ID", "SUPABASE_S3_SECRET_ACCESS_KEY",
            "SUPABASE_S3_ENDPOINT_URL", "SUPABASE_S3_REGION_NAME", "USE_SUPABASE_STORAGE",
        ):
            env.pop(name, None)
        env.update({"VERCEL": "1", "DEBUG": "0", "SECRET_KEY": "test-secret-key"})
        return env

    def test_vercel_requires_database_url(self):
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=settings.BASE_DIR, env=self.vercel_environment(), capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL es obligatoria en Vercel", result.stderr)

    def test_pooler_and_private_storage_options(self):
        env = self.vercel_environment()
        env.update({
            "DATABASE_URL": "postgresql://user:password@pooler.example:6543/postgres",
            "SUPABASE_S3_ACCESS_KEY_ID": "access",
            "SUPABASE_S3_SECRET_ACCESS_KEY": "secret",
            "SUPABASE_S3_ENDPOINT_URL": "https://project.storage.supabase.co/storage/v1/s3",
            "SUPABASE_S3_REGION_NAME": "us-east-1",
        })
        code = (
            "import json; from config import settings as s; "
            "d=s.DATABASES['default']; o=s.STORAGES['default']['OPTIONS']; "
            "print(json.dumps({'engine':d['ENGINE'],'age':d['CONN_MAX_AGE'],"
            "'cursors':d['DISABLE_SERVER_SIDE_CURSORS'],'db_options':d['OPTIONS'],"
            "'bucket':o['bucket_name'],'auth':o['querystring_auth']}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=settings.BASE_DIR, env=env,
            capture_output=True, text=True, check=True,
        )
        configured = json.loads(result.stdout)
        self.assertEqual(configured["engine"], "django.db.backends.postgresql")
        self.assertEqual(configured["age"], 0)
        self.assertTrue(configured["cursors"])
        self.assertEqual(configured["db_options"]["sslmode"], "require")
        self.assertIsNone(configured["db_options"]["prepare_threshold"])
        self.assertEqual(configured["bucket"], "eventos")
        self.assertTrue(configured["auth"])
