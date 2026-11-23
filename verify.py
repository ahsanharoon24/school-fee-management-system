"""verify.py — School Fee Management end-to-end verification (throwaway temp DB).

Run:  venv\\Scripts\\python verify.py        (exit 0 = sab pass)
Real data file (school.db) kabhi touch nahi hota.
"""
import os
import sys
import sqlite3
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)

import app as m

fd, tmp = tempfile.mkstemp(suffix='.db')
os.close(fd)
m.DB_PATH = tmp

fails = []


def check(name, cond, extra=''):
    print(('PASS' if cond else 'FAIL'), '|', name, extra)
    if not cond:
        fails.append(name)


def q(sql, args=()):
    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row
    r = conn.execute(sql, args).fetchall()
    conn.close()
    return r


def main():
    m.init_db()
    m.seed_admin()
    c = m.app.test_client()

    r = c.post('/login', data={'username': 'admin', 'password': 'admin123'})
    check('login', r.status_code == 302)

    with m.get_db() as conn:
        conn.execute("INSERT INTO classes (name, monthly_fee) VALUES ('Nursery', 4000)")
        conn.execute("INSERT INTO classes (name, monthly_fee) VALUES ('Class 1', 5000)")
        conn.execute("INSERT INTO students (name, father_name, class_id, roll_no) "
                     "VALUES ('Ali', 'Hassan', 1, 'N-1')")
        conn.execute("INSERT INTO students (name, father_name, class_id, roll_no) "
                     "VALUES ('Ayesha', 'Khan', 1, 'N-2')")
        conn.execute("INSERT INTO students (name, father_name, class_id, roll_no) "
                     "VALUES ('Bilal', 'Akhtar', 2, 'C-1')")
        conn.execute("INSERT INTO students (name, father_name, class_id, roll_no, "
                     "fee_override) VALUES ('Zara', 'Sami', 2, 'C-2', 5500)")

    # --- generate: 4 challans, numbering, snapshots, override ---
    c.post('/challans/generate', data={'month': '2026-09'})
    rows = q('SELECT * FROM challans ORDER BY id')
    check('generate -> 4 challans', len(rows) == 4)
    check('numbering SF-2026-0001..0004',
          [r['challan_number'] for r in rows] == [f'SF-2026-{i:04d}' for i in range(1, 5)])
    check('snapshot names', all(r['student_name'] for r in rows))
    check('class fee 4000', rows[0]['total'] == 4000, f"t={rows[0]['total']}")
    check('override 5500', rows[3]['total'] == 5500, f"t={rows[3]['total']}")

    # --- duplicate generation skips ---
    r = c.post('/challans/generate', data={'month': '2026-09'}, follow_redirects=True)
    check('re-generate skips all (still 4)', len(q('SELECT * FROM challans')) == 4)
    check('skip message shown', b'skip' in r.data)

    # --- next month: numbering continues ---
    c.post('/challans/generate', data={'month': '2026-10'})
    rows2 = q('SELECT * FROM challans ORDER BY id')
    check('next month numbers 0005-0008', rows2[4]['challan_number'] == 'SF-2026-0005')

    # --- payments: partial -> full, overpayment block ---
    c.post('/challans/1/payment', data={'amount': '1500', 'payment_date': '2026-09-05',
                                        'method': 'cash', 'reference': ''})
    check('partial -> partially_paid',
          q('SELECT status FROM challans WHERE id = 1')[0]['status'] == 'partially_paid')
    r = c.post('/challans/1/payment', data={'amount': '99999', 'payment_date': '2026-09-05',
                                            'method': 'cash', 'reference': ''},
               follow_redirects=True)
    check('overpayment blocked', b'Overpayment' in r.data)
    c.post('/challans/1/payment', data={'amount': '2500', 'payment_date': '2026-09-06',
                                        'method': 'bank', 'reference': 'TXN1'})
    check('full -> paid', q('SELECT status FROM challans WHERE id = 1')[0]['status'] == 'paid')
    check('2 payments recorded', len(q('SELECT * FROM payments WHERE challan_id = 1')) == 2)

    # --- cancel rules ---
    c.post('/challans/1/cancel')
    check('paid challan not cancellable',
          q('SELECT status FROM challans WHERE id = 1')[0]['status'] == 'paid')
    c.post('/challans/2/cancel')
    check('issued challan cancelled',
          q('SELECT status FROM challans WHERE id = 2')[0]['status'] == 'cancelled')
    c.post('/challans/2/payment', data={'amount': '1000', 'payment_date': '2026-09-07',
                                        'method': 'cash', 'reference': ''})
    check('payment on cancelled blocked',
          len(q('SELECT * FROM payments WHERE challan_id = 2')) == 0)

    # --- reports: billed excludes cancelled ---
    billed = q("SELECT SUM(total) s FROM challans WHERE is_deleted = 0 "
               "AND status != 'cancelled'")[0]['s']
    check('billed excludes cancelled (33000)', billed == 33000, f"billed={billed}")

    # --- left student skipped in next generation ---
    c.post('/students/4/toggle')
    c.post('/challans/generate', data={'month': '2026-11'})
    n = q("SELECT COUNT(*) n FROM challans WHERE billing_month = '2026-11'")[0]['n']
    check('left student skipped (3)', n == 3, f"n={n}")

    # --- all pages 200 ---
    for p in ['/', '/students', '/classes', '/challans', '/challans?month=2026-09',
              '/reports', '/settings', '/password', '/challans/1', '/challans/1/print',
              '/challans/3']:
        r = c.get(p)
        check(f'page {p}', r.status_code == 200, str(r.status_code))

    print(f'==== {39 - len(fails)} passed, {len(fails)} failed (of 39) ====')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
