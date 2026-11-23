-- School Fee Management System — SQLite schema (portfolio demo)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- SCHOOL SETTINGS (single row, id = 1)
-- ============================================================
CREATE TABLE IF NOT EXISTS school_settings (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    school_name     TEXT NOT NULL DEFAULT 'My School',
    address         TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    challan_footer  TEXT NOT NULL DEFAULT 'Please pay before the 10th of every month.',
    bank_name       TEXT NOT NULL DEFAULT '',
    account_title   TEXT NOT NULL DEFAULT '',
    account_number  TEXT NOT NULL DEFAULT '',
    late_fee        REAL NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- CLASSES (fee structure per class)
-- ============================================================
CREATE TABLE IF NOT EXISTS classes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,          -- "Nursery", "Class 5", "O-Level"
    monthly_fee REAL NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- STUDENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    father_name   TEXT NOT NULL DEFAULT '',
    class_id      INTEGER NOT NULL REFERENCES classes(id),
    roll_no       TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    address       TEXT NOT NULL DEFAULT '',
    fee_override  REAL,                         -- NULL = class fee use karo
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'left')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_students_name ON students(name);
CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_id);

-- ============================================================
-- CHALLANS (har student har mahine ka fee challan)
-- Fee amount SNAPSHOT — fee structure badalne se purane challan nahi badalte.
-- ============================================================
CREATE TABLE IF NOT EXISTS challans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    challan_number  TEXT NOT NULL UNIQUE,       -- SF-2026-0001
    student_id      INTEGER NOT NULL REFERENCES students(id),
    billing_month   TEXT NOT NULL,              -- 'YYYY-MM'
    -- snapshots
    student_name    TEXT NOT NULL,
    class_name      TEXT NOT NULL,
    monthly_fee     REAL NOT NULL DEFAULT 0,
    late_fee        REAL NOT NULL DEFAULT 0,
    total           REAL NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'issued'
                    CHECK (status IN ('issued', 'partially_paid', 'paid', 'cancelled')),
    issued_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_deleted      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_challans_student ON challans(student_id);
CREATE INDEX IF NOT EXISTS idx_challans_month  ON challans(billing_month);
CREATE INDEX IF NOT EXISTS idx_challans_status ON challans(status);
-- Ek student ka ek mahine mein sirf ek live challan
CREATE UNIQUE INDEX IF NOT EXISTS uq_challan_student_month
    ON challans(student_id, billing_month)
    WHERE status != 'cancelled' AND is_deleted = 0;

-- ============================================================
-- PAYMENTS (partial payments allowed)
-- ============================================================
CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    challan_id   INTEGER NOT NULL REFERENCES challans(id),
    amount       REAL NOT NULL CHECK (amount > 0),
    method       TEXT NOT NULL DEFAULT 'cash' CHECK (method IN ('cash', 'bank', 'online')),
    reference    TEXT NOT NULL DEFAULT '',
    payment_date TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_payments_challan ON payments(challan_id);

-- ============================================================
-- CHALLAN NUMBER SEQUENCE (transaction-safe, har saal 1 se)
-- ============================================================
CREATE TABLE IF NOT EXISTS challan_sequences (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    prefix      TEXT NOT NULL,
    year        TEXT NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- SEED
-- ============================================================
INSERT OR IGNORE INTO school_settings (id, school_name, challan_footer)
VALUES (1, 'My School', 'Please pay before the 10th of every month.');

INSERT OR IGNORE INTO challan_sequences (id, prefix, year, last_number)
VALUES (1, 'SF', '', 0);
