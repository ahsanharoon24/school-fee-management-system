"""School Fee Management — students, classes, monthly challans, payments, dues.

Single-file Flask app (portfolio demo). Run: run.bat
Login: admin / admin123
"""
import os
import sqlite3
from datetime import datetime

from flask import (Flask, abort, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'school.db')

# --- Serverless (Vercel) support: only /tmp is writable -----------------
# The bundled demo database is copied to /tmp on cold start so that
# login/write flows work. Data resets when the instance recycles.
if os.environ.get('VERCEL'):
    import shutil
    DB_PATH = '/tmp/school.db'
    _src = os.path.join(BASE_DIR, 'school.db')
    if not os.path.exists(DB_PATH) and os.path.exists(_src):
        shutil.copyfile(_src, DB_PATH)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'school-demo-secret-change-me')


# ==================================================================
# DB helpers
# ==================================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(open(os.path.join(BASE_DIR, 'schema.sql'),
                                encoding='utf-8').read())


def settings_row():
    with get_db() as conn:
        row = conn.execute('SELECT * FROM school_settings WHERE id = 1').fetchone()
        return dict(row) if row else {}


def month_label(ym):
    """'2026-09' -> 'September 2026'"""
    try:
        from datetime import datetime as dt
        return dt.strptime(ym, '%Y-%m').strftime('%B %Y')
    except Exception:
        return ym


def paid_amount(conn, challan_id):
    row = conn.execute('SELECT COALESCE(SUM(amount), 0) s FROM payments '
                       'WHERE challan_id = ?', (challan_id,)).fetchone()
    return row['s']


def refresh_status(conn, challan_id, total):
    paid = paid_amount(conn, challan_id)
    if paid >= total:
        status = 'paid'
    elif paid > 0:
        status = 'partially_paid'
    else:
        status = 'issued'
    conn.execute('UPDATE challans SET status = ? WHERE id = ?', (status, challan_id))
    return status


# ==================================================================
# Auth
# ==================================================================
@app.context_processor
def inject_globals():
    return dict(settings=settings_row(), month_label=month_label)


def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user, pw = request.form.get('username', '').strip(), request.form.get('password', '')
        with get_db() as conn:
            row = conn.execute('SELECT * FROM users WHERE username = ?', (user,)).fetchone()
        if row and check_password_hash(row['password_hash'], pw):
            session['user'] = dict(row)
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Wrong username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==================================================================
# Dashboard
# ==================================================================
@app.route('/')
@login_required
def dashboard():
    this_month = datetime.now().strftime('%Y-%m')
    with get_db() as conn:
        students = conn.execute(
            "SELECT COUNT(*) c FROM students WHERE status = 'active'").fetchone()['c']
        billed = conn.execute(
            'SELECT COALESCE(SUM(total),0) s, COUNT(*) c FROM challans '
            'WHERE billing_month = ? AND is_deleted = 0 AND status != ?',
            (this_month, 'cancelled')).fetchone()
        collected = conn.execute(
            "SELECT COALESCE(SUM(p.amount),0) s FROM payments p "
            "JOIN challans ch ON ch.id = p.challan_id "
            "WHERE ch.billing_month = ? AND p.payment_date LIKE ?",
            (this_month, datetime.now().strftime('%Y-%m') + '%')).fetchone()['s']
        paid_rows = conn.execute(
            "SELECT COUNT(*) c FROM challans WHERE billing_month = ? "
            "AND status = 'paid' AND is_deleted = 0", (this_month,)).fetchone()['c']
        outstanding = billed['s'] - collected
        recent = conn.execute(
            'SELECT * FROM challans WHERE is_deleted = 0 ORDER BY id DESC LIMIT 8').fetchall()
        dues_map = {r['id']: r for r in conn.execute(
            'SELECT c.id, c.total, COALESCE(SUM(p.amount),0) paid '
            'FROM challans c LEFT JOIN payments p ON p.challan_id = c.id '
            "WHERE c.status IN ('issued','partially_paid') AND c.is_deleted = 0 "
            'GROUP BY c.id').fetchall()}
    return render_template('dashboard.html', students=students, this_month=this_month,
                           billed=billed['s'], billed_count=billed['c'],
                           collected=collected, outstanding=outstanding,
                           paid_count=paid_rows, recent=recent, dues_map=dues_map)


# ==================================================================
# Classes (fee structure)
# ==================================================================
@app.route('/classes', methods=['GET', 'POST'])
@login_required
def classes_page():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        try:
            fee = float(request.form.get('monthly_fee', '0') or 0)
        except ValueError:
            fee = 0
        if not name:
            flash('Class name required.', 'error')
        else:
            try:
                with get_db() as conn:
                    conn.execute('INSERT INTO classes (name, monthly_fee) VALUES (?, ?)',
                                 (name, fee))
                flash(f'Class "{name}" added.', 'success')
            except sqlite3.IntegrityError:
                flash('Class name already exists.', 'error')
        return redirect(url_for('classes_page'))
    with get_db() as conn:
        classes = conn.execute('SELECT * FROM classes ORDER BY name').fetchall()
        counts = {r['class_id']: r['c'] for r in conn.execute(
            "SELECT class_id, COUNT(*) c FROM students WHERE status = 'active' "
            'GROUP BY class_id').fetchall()}
    return render_template('classes.html', classes=classes, counts=counts)


@app.route('/classes/<int:cid>/edit', methods=['POST'])
@login_required
def class_edit(cid):
    try:
        fee = float(request.form.get('monthly_fee', '0') or 0)
    except ValueError:
        fee = 0
    with get_db() as conn:
        conn.execute('UPDATE classes SET monthly_fee = ? WHERE id = ?', (fee, cid))
    flash('Fee updated. (Old challans keep their original amount — snapshot.)', 'success')
    return redirect(url_for('classes_page'))


# ==================================================================
# Students
# ==================================================================
@app.route('/students', methods=['GET', 'POST'])
@login_required
def students_page():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        father = request.form.get('father_name', '').strip()
        class_id = request.form.get('class_id')
        roll = request.form.get('roll_no', '').strip()
        phone = request.form.get('phone', '').strip()
        addr = request.form.get('address', '').strip()
        override = request.form.get('fee_override', '').strip()
        if not name or not class_id:
            flash('Student name and class are required.', 'error')
        else:
            with get_db() as conn:
                conn.execute(
                    'INSERT INTO students (name, father_name, class_id, roll_no, phone, '
                    'address, fee_override) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (name, father, class_id, roll, phone, addr,
                     float(override) if override else None))
            flash(f'Student "{name}" added.', 'success')
        return redirect(url_for('students_page'))
    q = request.args.get('q', '').strip()
    with get_db() as conn:
        classes = {r['id']: r for r in conn.execute('SELECT * FROM classes').fetchall()}
        if q:
            rows = conn.execute(
                'SELECT * FROM students WHERE name LIKE ? OR father_name LIKE ? '
                'OR roll_no LIKE ? OR phone LIKE ? ORDER BY name LIMIT 100',
                (f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
        else:
            rows = conn.execute('SELECT * FROM students ORDER BY name').fetchall()
    return render_template('students.html', students=rows, classes=classes, q=q)


@app.route('/students/<int:sid>/toggle', methods=['POST'])
@login_required
def student_toggle(sid):
    with get_db() as conn:
        conn.execute("UPDATE students SET status = CASE WHEN status = 'active' "
                     "THEN 'left' ELSE 'active' END WHERE id = ?", (sid,))
    return redirect(request.referrer or url_for('students_page'))


# ==================================================================
# Challans
# ==================================================================
def next_challan_number(conn, now):
    year = now.strftime('%Y')
    row = conn.execute('SELECT * FROM challan_sequences WHERE id = 1').fetchone()
    n = (row['last_number'] + 1) if row and row['year'] == year else 1
    conn.execute(
        'INSERT INTO challan_sequences (id, prefix, year, last_number) VALUES (1, ?, ?, ?) '
        'ON CONFLICT(id) DO UPDATE SET prefix = excluded.prefix, '
        'year = excluded.year, last_number = excluded.last_number',
        ('SF', year, n))
    return f'SF-{year}-{n:04d}'


@app.route('/challans')
@login_required
def challan_list():
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    status = request.args.get('status', '')
    class_id = request.args.get('class_id', '')
    q = ("SELECT c.* FROM challans c JOIN students s ON s.id = c.student_id "
         "WHERE c.is_deleted = 0 AND c.billing_month = ?")
    args = [month]
    if status in ('issued', 'partially_paid', 'paid', 'cancelled'):
        q += ' AND c.status = ?'
        args.append(status)
    if class_id:
        q += ' AND s.class_id = ?'
        args.append(class_id)
    q += ' ORDER BY c.class_name, c.student_name'
    with get_db() as conn:
        challans = conn.execute(q, args).fetchall()
        classes = conn.execute('SELECT * FROM classes ORDER BY name').fetchall()
        paid_map = {r['challan_id']: r['s'] for r in conn.execute(
            'SELECT challan_id, SUM(amount) s FROM payments GROUP BY challan_id').fetchall()}
    return render_template('challans/list.html', challans=challans, month=month,
                           status=status, class_id=class_id, classes=classes,
                           paid_map=paid_map)


@app.route('/challans/generate', methods=['POST'])
@login_required
def challan_generate():
    """Generate monthly challans for the whole school with one click.
    Duplicate protection: students who already have one are skipped."""
    month = request.form.get('month', datetime.now().strftime('%Y-%m'))
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        students = conn.execute(
            "SELECT * FROM students WHERE status = 'active' ORDER BY name").fetchall()
        existing = {r['student_id'] for r in conn.execute(
            'SELECT student_id FROM challans WHERE billing_month = ? '
            "AND is_deleted = 0 AND status != 'cancelled'", (month,)).fetchall()}
        created = 0
        skipped = 0
        for st in students:
            if st['id'] in existing:
                skipped += 1
                continue
            class_row = conn.execute('SELECT * FROM classes WHERE id = ?',
                                     (st['class_id'],)).fetchone()
            fee = st['fee_override'] if st['fee_override'] is not None \
                else (class_row['monthly_fee'] if class_row else 0)
            number = next_challan_number(conn, datetime.now())
            conn.execute(
                'INSERT INTO challans (challan_number, student_id, billing_month, '
                'student_name, class_name, monthly_fee, late_fee, total) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (number, st['id'], month, st['name'],
                 class_row['name'] if class_row else '', fee, 0, fee))
            created += 1
        conn.commit()
    flash(f'{created} challans created, {skipped} skipped (already exist). Month: {month_label(month)}',
          'success')
    return redirect(url_for('challan_list', month=month))


@app.route('/challans/<int:cid>')
@login_required
def challan_view(cid):
    with get_db() as conn:
        challan = conn.execute('SELECT * FROM challans WHERE id = ?', (cid,)).fetchone()
        if not challan:
            abort(404)
        payments = conn.execute('SELECT * FROM payments WHERE challan_id = ? '
                                'ORDER BY id DESC', (cid,)).fetchall()
        paid = paid_amount(conn, cid)
        student = conn.execute('SELECT * FROM students WHERE id = ?',
                               (challan['student_id'],)).fetchone()
    return render_template('challans/view.html', ch=challan, payments=payments,
                           paid=paid, due=max(challan['total'] - paid, 0), student=student)


@app.route('/challans/<int:cid>/payment', methods=['POST'])
@login_required
def challan_payment(cid):
    try:
        amount = float(request.form.get('amount', '0') or 0)
    except ValueError:
        amount = 0
    method = request.form.get('method', 'cash')
    if method not in ('cash', 'bank', 'online'):
        method = 'cash'
    pay_date = request.form.get('payment_date', datetime.now().strftime('%Y-%m-%d'))
    with get_db() as conn:
        challan = conn.execute('SELECT * FROM challans WHERE id = ?', (cid,)).fetchone()
        if not challan or challan['status'] == 'cancelled':
            flash('Challan not found or already cancelled.', 'error')
            return redirect(url_for('challan_list'))
        paid = paid_amount(conn, cid)
        if amount <= 0:
            flash('Amount must be greater than zero.', 'error')
            return redirect(url_for('challan_view', cid=cid))
        if amount > challan['total'] - paid:
            flash(f'Overpayment blocked — only Rs. {challan["total"] - paid:,.2f} remaining.',
                  'error')
            return redirect(url_for('challan_view', cid=cid))
        conn.execute('INSERT INTO payments (challan_id, amount, method, reference, '
                     'payment_date) VALUES (?, ?, ?, ?, ?)',
                     (cid, amount, method, request.form.get('reference', ''), pay_date))
        refresh_status(conn, cid, challan['total'])
    flash(f'Payment recorded — Rs. {amount:,.2f}.', 'success')
    return redirect(url_for('challan_view', cid=cid))


@app.route('/challans/<int:cid>/cancel', methods=['POST'])
@login_required
def challan_cancel(cid):
    with get_db() as conn:
        challan = conn.execute('SELECT * FROM challans WHERE id = ?', (cid,)).fetchone()
        if challan and challan['status'] in ('issued',):
            conn.execute("UPDATE challans SET status = 'cancelled' WHERE id = ?", (cid,))
            flash('Challan cancelled.', 'success')
        else:
            flash('Only issued challans can be cancelled (not ones with payments).', 'error')
    return redirect(url_for('challan_view', cid=cid))


@app.route('/challans/<int:cid>/print')
@login_required
def challan_print(cid):
    with get_db() as conn:
        ch = conn.execute('SELECT * FROM challans WHERE id = ?', (cid,)).fetchone()
        if not ch:
            abort(404)
        student = conn.execute('SELECT * FROM students WHERE id = ?',
                               (ch['student_id'],)).fetchone()
    return render_template('challans/print.html', ch=ch, student=student,
                           settings=settings_row())


# ==================================================================
# Reports
# ==================================================================
@app.route('/reports')
@login_required
def reports():
    year = request.args.get('year', datetime.now().strftime('%Y'))
    with get_db() as conn:
        monthly = conn.execute(
            "SELECT ch.billing_month m, COUNT(DISTINCT ch.id) challans, "
            "COALESCE(SUM(ch.total),0) billed, "
            "COALESCE((SELECT SUM(p.amount) FROM payments p JOIN challans c2 "
            "ON c2.id = p.challan_id WHERE c2.billing_month = ch.billing_month),0) collected "
            "FROM challans ch WHERE ch.billing_month LIKE ? AND ch.is_deleted = 0 "
            "AND ch.status != 'cancelled' GROUP BY ch.billing_month ORDER BY m",
            (f'{year}%',)).fetchall()
        by_class = conn.execute(
            "SELECT class_name, COUNT(*) challans, SUM(total) billed, "
            "SUM(CASE WHEN status IN ('issued','partially_paid') THEN 1 ELSE 0 END) unpaid "
            "FROM challans WHERE billing_month LIKE ? AND is_deleted = 0 "
            "AND status != 'cancelled' GROUP BY class_name ORDER BY billed DESC",
            (f'{year}%',)).fetchall()
        defaulters = conn.execute(
            "SELECT c.student_name, c.class_name, c.billing_month, c.total, "
            "COALESCE(SUM(p.amount),0) paid FROM challans c "
            "LEFT JOIN payments p ON p.challan_id = c.id "
            "WHERE c.status IN ('issued','partially_paid') AND c.is_deleted = 0 "
            "GROUP BY c.id ORDER BY c.billing_month DESC, c.student_name LIMIT 50").fetchall()
    return render_template('reports.html', monthly=monthly, by_class=by_class,
                           defaulters=defaulters, year=year, month_label=month_label)


# ==================================================================
# Settings + password
# ==================================================================
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    if request.method == 'POST':
        fields = ('school_name', 'address', 'phone', 'email', 'challan_footer',
                  'bank_name', 'account_title', 'account_number')
        data = {k: request.form.get(k, '') for k in fields}
        try:
            data['late_fee'] = float(request.form.get('late_fee', '0') or 0)
        except ValueError:
            data['late_fee'] = 0
        with get_db() as conn:
            conn.execute(
                'UPDATE school_settings SET school_name = ?, address = ?, phone = ?, '
                'email = ?, challan_footer = ?, bank_name = ?, account_title = ?, '
                'account_number = ?, late_fee = ? WHERE id = 1',
                (data['school_name'], data['address'], data['phone'], data['email'],
                 data['challan_footer'], data['bank_name'], data['account_title'],
                 data['account_number'], data['late_fee']))
        flash('Settings saved.', 'success')
        return redirect(url_for('settings_page'))
    return render_template('settings.html', s=settings_row())


@app.route('/password', methods=['GET', 'POST'])
@login_required
def password():
    if request.method == 'POST':
        old, new, confirm = (request.form.get('old_password', ''),
                             request.form.get('new_password', ''),
                             request.form.get('confirm_password', ''))
        with get_db() as conn:
            row = conn.execute('SELECT * FROM users WHERE id = ?',
                               (session['user']['id'],)).fetchone()
        if not check_password_hash(row['password_hash'], old):
            flash('Old password wrong.', 'error')
        elif len(new) < 6:
            flash('New password must be at least 6 characters.', 'error')
        elif new != confirm:
            flash('Passwords do not match.', 'error')
        else:
            with get_db() as conn:
                conn.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                             (generate_password_hash(new), session['user']['id']))
            flash('Password changed.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('password.html')


def seed_admin():
    with get_db() as conn:
        if not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            conn.execute('INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)',
                         ('admin', generate_password_hash('admin123'), 'Administrator'))
            print('=' * 56)
            print('  DEFAULT LOGIN: admin / admin123')
            print('=' * 56)


if __name__ == '__main__':
    init_db()
    seed_admin()
    app.run(host='0.0.0.0', port=5002, debug=False)
