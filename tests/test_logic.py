"""Проверка логики без Kivy: python -m unittest discover -s tests"""
import json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models import Ledger, INCOME, EXPENSE
from cloud import CloudSync, CloudError
import charts


class FakeFirebase(BaseHTTPRequestHandler):
    store = None

    def log_message(self, *a): pass

    def do_GET(self):
        body = json.dumps(FakeFirebase.store).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)

    def do_PUT(self):
        n = int(self.headers["Content-Length"])
        FakeFirebase.store = json.loads(self.rfile.read(n))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.l = Ledger(os.path.join(self.dir, "t.json"))

    def test_balance_and_categories(self):
        self.l.add(INCOME, "Продажи", "a", "1000")
        self.l.add(INCOME, "Услуги", "b", 500)
        self.l.add(EXPENSE, "Офис", "c", "300,5")
        self.assertEqual(self.l.total(INCOME), 1500)
        self.assertEqual(self.l.total(EXPENSE), 300.5)
        self.assertEqual(self.l.balance(), 1199.5)
        self.assertEqual(list(self.l.by_category(INCOME)), ["Продажи", "Услуги"])

    def test_validation(self):
        for args in [(INCOME, "Офис", "x", 5), (EXPENSE, "Офис", "x", "abc"), (EXPENSE, "Офис", "x", 0), ("zz", "Офис", "x", 1)]:
            with self.assertRaises(ValueError):
                self.l.add(*args)

    def test_persistence_and_delete(self):
        tx = self.l.add(EXPENSE, "Офис", "x", 100)
        self.l.delete(tx.id)
        again = Ledger(self.l.path)
        self.assertEqual(again.active(), [])
        self.assertEqual(len(again.all()), 1)

    def test_csv(self):
        self.l.add(INCOME, "Продажи", "a", 10)
        p = self.l.export_csv(os.path.join(self.dir, "e.csv"))
        with open(p, encoding="utf-8-sig") as f:
            self.assertIn("Продажи", f.read())


class CloudTests(unittest.TestCase):
    def test_two_devices_sync(self):
        FakeFirebase.store = None
        srv = HTTPServer(("127.0.0.1", 0), FakeFirebase)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}"
        d = tempfile.mkdtemp()
        a, b = Ledger(os.path.join(d, "a.json")), Ledger(os.path.join(d, "b.json"))
        t1 = a.add(INCOME, "Продажи", "с телефона", 1000)
        CloudSync(url).sync(a)
        received, total = CloudSync(url).sync(b)
        self.assertEqual((received, total), (1, 1))
        b.add(EXPENSE, "Офис", "с планшета", 200)
        b.delete(t1.id)
        CloudSync(url).sync(b)
        CloudSync(url).sync(a)
        self.assertEqual([t.description for t in a.active()], ["с планшета"])
        self.assertEqual(a.balance(), -200)
        srv.shutdown()

    def test_errors(self):
        with self.assertRaises(CloudError):
            CloudSync("").sync(Ledger(os.path.join(tempfile.mkdtemp(), "x.json")))
        with self.assertRaises(CloudError):
            CloudSync("http://127.0.0.1:1", timeout=1).sync(Ledger(os.path.join(tempfile.mkdtemp(), "y.json")))


class ChartTests(unittest.TestCase):
    def test_render(self):
        d = tempfile.mkdtemp()
        l = Ledger(os.path.join(d, "t.json"))
        for fig in (charts.pie_by_category(l, EXPENSE), charts.income_vs_expense(l)):
            fig.savefig(os.path.join(d, "empty.png"))
        l.add(INCOME, "Продажи", "a", 1000); l.add(EXPENSE, "Офис", "b", 400); l.add(EXPENSE, "Налоги", "c", 100)
        for i, fig in enumerate((charts.pie_by_category(l, EXPENSE), charts.pie_by_category(l, INCOME), charts.income_vs_expense(l))):
            fig.savefig(os.path.join(os.environ.get("OUT", d), f"chart{i}.png"))


if __name__ == "__main__":
    unittest.main()
