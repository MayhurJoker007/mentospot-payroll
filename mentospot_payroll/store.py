"""Pay runs in SQLite. A run is built, checked, then locked. Locked runs can't be recalculated, so what was
paid and what's on record can't drift apart.
"""
import json
import sqlite3
from datetime import date
from decimal import Decimal as D

from .engine import Employee, Line, PayrollError, Payslip, PeriodInputs, calculate

SCHEMA = """
CREATE TABLE IF NOT EXISTS employee (
    number      TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pay_run (
    period      TEXT PRIMARY KEY,          -- YYYY-MM
    status      TEXT NOT NULL CHECK (status IN ('draft', 'locked')),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at   TEXT
);
CREATE TABLE IF NOT EXISTS payslip (
    period      TEXT NOT NULL REFERENCES pay_run (period),
    employee    TEXT NOT NULL REFERENCES employee (number),
    gross       TEXT NOT NULL,
    paye        TEXT NOT NULL,
    uif         TEXT NOT NULL,
    net         TEXT NOT NULL,
    taxable     TEXT NOT NULL,             -- regular|irregular
    snapshot    TEXT NOT NULL,             -- employee record as it was when calculated
    lines       TEXT NOT NULL,
    PRIMARY KEY (period, employee)
);
"""

_DECIMAL_FIELDS = {'monthly_salary', 'medical_aid_employee', 'medical_aid_employer', 'pension_employee',
                   'travel_allowance', 'tax_directive_rate'}


def _encode(emp):
    d = dict(emp.__dict__)
    d['born'] = emp.born.isoformat()
    return json.dumps({k: (str(v) if isinstance(v, D) else v) for k, v in d.items()})


def _decode(text):
    d = json.loads(text)
    d['born'] = date.fromisoformat(d['born'])
    for k in _DECIMAL_FIELDS:
        if d.get(k) is not None:
            d[k] = D(d[k])
    return Employee(**d)


class PayrollStore:
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def save_employee(self, emp):
        with self.db:
            self.db.execute('INSERT INTO employee (number, data) VALUES (?, ?) '
                            'ON CONFLICT (number) DO UPDATE SET data = excluded.data', (emp.number, _encode(emp)))

    def deactivate(self, number):
        with self.db:
            self.db.execute('UPDATE employee SET active = 0 WHERE number = ?', (number,))

    def employees(self):
        return [_decode(r[0]) for r in self.db.execute('SELECT data FROM employee WHERE active = 1 ORDER BY number')]

    def run(self, period, inputs=None):
        """(Re)calculate a draft run for every active employee. inputs: {employee number: PeriodInputs}."""
        key = period.strftime('%Y-%m')
        status = self.db.execute('SELECT status FROM pay_run WHERE period = ?', (key,)).fetchone()
        if status and status[0] == 'locked':
            raise PayrollError('Pay run %s is locked' % key)

        inputs = inputs or {}
        unknown = set(inputs) - {e.number for e in self.employees()}
        if unknown:
            raise PayrollError('Inputs for unknown or inactive employees: %s' % ', '.join(sorted(unknown)))

        slips = [calculate(e, period, inputs.get(e.number, PeriodInputs())) for e in self.employees()]
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO pay_run (period, status) VALUES (?, ?)', (key, 'draft'))
            self.db.execute('DELETE FROM payslip WHERE period = ?', (key,))
            self.db.executemany(
                'INSERT INTO payslip (period, employee, gross, paye, uif, net, taxable, snapshot, lines) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [(key, s.employee.number, str(s.gross), str(s.paye), str(s.uif), str(s.net),
                  '%s|%s' % (s.taxable_regular, s.taxable_irregular), _encode(s.employee), json.dumps({
                    'earnings': [[l.code, l.label, str(l.amount)] for l in s.earnings],
                    'deductions': [[l.code, l.label, str(l.amount)] for l in s.deductions],
                    'employer': [[l.code, l.label, str(l.amount)] for l in s.employer],
                })) for s in slips])
        return slips

    def lock(self, period):
        key = period.strftime('%Y-%m')
        with self.db:
            cur = self.db.execute("UPDATE pay_run SET status = 'locked', locked_at = CURRENT_TIMESTAMP "
                                  "WHERE period = ? AND status = 'draft'", (key,))
        if cur.rowcount == 0:
            raise PayrollError('No draft pay run for %s' % key)

    def payslips(self, period):
        """The payslips as stored for a run, rebuilt from the database rather than recalculated."""
        key = period.strftime('%Y-%m')
        slips = []
        for gross, paye, uif, net, taxable, snapshot, lines in self.db.execute(
                'SELECT gross, paye, uif, net, taxable, snapshot, lines FROM payslip WHERE period = ? ORDER BY employee',
                (key,)):
            data = json.loads(lines)
            regular, irregular = taxable.split('|')
            as_lines = lambda rows: [Line(c, l, D(a)) for c, l, a in rows]
            slips.append(Payslip(_decode(snapshot), period, as_lines(data['earnings']), as_lines(data['deductions']),
                                 as_lines(data['employer']), D(gross), D(regular), D(irregular), D(paye), D(uif), D(net)))
        return slips

    def summary(self, period):
        slips = self.payslips(period)
        return {
            'employees': len(slips),
            'gross': sum((s.gross for s in slips), D(0)),
            'paye': sum((s.paye for s in slips), D(0)),
            'uif': sum((s.uif for s in slips), D(0)),
            'net': sum((s.net for s in slips), D(0)),
        }

    def year_to_date(self, number, period):
        """Totals per IRP5 source code from March of the tax year up to and including period."""
        start = date(period.year if period.month >= 3 else period.year - 1, 3, 1).strftime('%Y-%m')
        end = period.strftime('%Y-%m')
        totals = {}
        for (lines,) in self.db.execute('SELECT lines FROM payslip WHERE employee = ? AND period BETWEEN ? AND ?',
                                        (number, start, end)):
            data = json.loads(lines)
            for code, _, amount in data['earnings'] + data['deductions']:
                totals[code] = totals.get(code, D(0)) + D(amount)
        return dict(sorted(totals.items()))
