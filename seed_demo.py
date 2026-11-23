"""seed_demo.py — School Fee Management demo data.

Run:  venv\\Scripts\\python seed_demo.py
Login: admin / admin123
"""
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from app import app, init_db, seed_admin, get_db

CLASSES = [
    ('Nursery', 4000), ('Prep', 4500), ('Class 1', 5000),
    ('Class 2', 5500), ('Class 3', 6000), ('Class 4', 6500), ('Class 5', 7000),
]

STUDENTS = [
    # (name, father, class_idx, roll, phone)
    ('Ali Hassan',      'Muhammad Hassan',   0, 'N-01', '0300-1112233'),
    ('Ayesha Khan',     'Imran Khan',        0, 'N-02', '0321-4445566'),
    ('Hamza Tariq',     'Tariq Mehmood',     1, 'P-01', '0333-7778899'),
    ('Fatima Noor',     'Noor Ahmed',        1, 'P-02', '0345-2223344'),
    ('Usman Ghani',     'Abdul Ghani',       2, '1-01', '0301-5556677'),
    ('Zara Sheikh',     'Sami Sheikh',       2, '1-02', '0322-8889900'),
    ('Bilal Akhtar',    'Akhtar Ali',        3, '2-01', '0334-1234567'),
    ('Mahnoor Aslam',   'Aslam Pervez',      3, '2-02', '0346-7654321'),
    ('Rayan Iqbal',     'Iqbal Hussain',     4, '3-01', '0302-9990001'),
    ('Hira Saeed',      'Saeed Anwar',       4, '3-02', '0323-1110002'),
    ('Daniyal Raza',    'Raza Abbas',        5, '4-01', '0335-2220003'),
    ('Sana Javed',      'Javed Iqbal',       5, '4-02', '0347-3330004'),
    ('Omar Farooq',     'Farooq Ahmed',      6, '5-01', '0303-4440005'),
    ('Laiba Malik',     'Malik Naveed',      6, '5-02', '0324-5550006'),
]


def main():
    init_db()
    seed_admin()

    with get_db() as conn:
        conn.execute(
            "UPDATE school_settings SET school_name = 'Al-Noor Public School', "
            "address = 'Street 4, Model Town, Lahore', phone = '+92 42 3585 1234', "
            "email = 'info@alnoorps.edu.pk', "
            "bank_name = 'Bank Alfalah', account_title = 'Al-Noor Public School', "
            "account_number = '0022-1234567-01', late_fee = 0 WHERE id = 1")
        for name, fee in CLASSES:
            conn.execute('INSERT OR IGNORE INTO classes (name, monthly_fee) VALUES (?, ?)',
                         (name, fee))
        class_map = {r['name']: r['id'] for r in
                     conn.execute('SELECT id, name FROM classes').fetchall()}
        for name, father, ci, roll, phone in STUDENTS:
            conn.execute(
                'INSERT INTO students (name, father_name, class_id, roll_no, phone) '
                'VALUES (?, ?, ?, ?, ?)',
                (name, father, class_map[CLASSES[ci][0]], roll, phone))

    client = app.test_client()
    r = client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    assert r.status_code == 302, 'login failed'

    # Is mahine ke challans generate (sab students)
    this_month = datetime.now().strftime('%Y-%m')
    r = client.post('/challans/generate', data={'month': this_month})
    assert r.status_code == 302, 'challan generation failed'

    # ~70% students pay (dashboard par collected/outstanding dono dikhe)
    with get_db() as conn:
        challans = conn.execute('SELECT id, total FROM challans ORDER BY id').fetchall()
    pay_count = int(len(challans) * 0.7)
    pay_date = datetime.now().strftime('%Y-%m-%d')
    for ch in challans[:pay_count]:
        r = client.post(f'/challans/{ch["id"]}/payment', data={
            'amount': str(ch['total']), 'payment_date': pay_date, 'method': 'cash',
            'reference': 'CASH'})
        assert r.status_code in (200, 302)

    print('=' * 56)
    print('  School Fee Management demo data ready!')
    print('  Login: admin / admin123')
    print(f'  7 classes, {len(STUDENTS)} students, {len(challans)} challans')
    print(f'  {pay_count} payments recorded (partial demo)')
    print('  Run:  run.bat  →  http://localhost:5002')
    print('=' * 56)


if __name__ == '__main__':
    main()
