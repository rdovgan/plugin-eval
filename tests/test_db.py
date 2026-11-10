import unittest

from evalkit import db


class ParseUrlTest(unittest.TestCase):
    def test_full_url(self):
        p = db.parse_url("mysql://plugin_eval:s%40cret@127.0.0.1:3307/plugin_eval")
        self.assertEqual(p, {"user": "plugin_eval", "password": "s@cret", "host": "127.0.0.1",
                             "port": 3307, "database": "plugin_eval"})

    def test_default_port(self):
        self.assertEqual(db.parse_url("mariadb://u:p@db.local/x")["port"], 3306)

    def test_rejects_garbage(self):
        with self.assertRaises(SystemExit):
            db.parse_url("postgres://u@h/x")


class MigrationsTest(unittest.TestCase):
    def test_versions_are_increasing(self):
        versions = [v for v, _ in db.MIGRATIONS]
        self.assertEqual(versions, sorted(set(versions)))


if __name__ == "__main__":
    unittest.main()
