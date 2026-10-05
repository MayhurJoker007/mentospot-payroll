"""
python -m mentospot_payroll import employees.csv            load or update employees
python -m mentospot_payroll run 2026-03 [--inputs vars.csv]  calculate a draft run
python -m mentospot_payroll lock 2026-03
python -m mentospot_payroll payslips 2026-03 --out payslips/

The database is payroll.db in the current folder unless --db is given.
"""
import argparse
import csv
import os
from datetime import date
from decimal import Decimal as D

from .engine import Employee, PayrollError, PeriodInputs
from .store import PayrollStore


def _period(text):
    y, m = text.split('-')
    return date(int(y), int(m), 1)


def _d(value, default='0'):
    return D(value.strip()) if value and value.strip() else D(default)


def import_employees(store, path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        store.save_employee(Employee(
            number=row['number'], name=row['name'], id_number=row.get('id_number', ''),
            born=date.fromisoformat(row['born']), monthly_salary=_d(row['monthly_salary']),
            medical_members=int(row.get('medical_members') or 0),
            medical_aid_employee=_d(row.get('medical_aid_employee')),
            medical_aid_employer=_d(row.get('medical_aid_employer')),
            pension_employee=_d(row.get('pension_employee')),
            travel_allowance=_d(row.get('travel_allowance')),
        ))
    return len(rows)


def read_inputs(path):
    if not path:
        return {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        return {row['number']: PeriodInputs(overtime=_d(row.get('overtime')), commission=_d(row.get('commission')),
                                            bonus=_d(row.get('bonus')), unpaid_leave_days=_d(row.get('unpaid_leave_days')))
                for row in csv.DictReader(f)}


def main():
    p = argparse.ArgumentParser(prog='mentospot_payroll')
    p.add_argument('--db', default='payroll.db')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('import').add_argument('csv')
    r = sub.add_parser('run')
    r.add_argument('period')
    r.add_argument('--inputs')
    sub.add_parser('lock').add_argument('period')
    ps = sub.add_parser('payslips')
    ps.add_argument('period')
    ps.add_argument('--out', default='payslips')
    args = p.parse_args()

    store = PayrollStore(args.db)
    try:
        if args.cmd == 'import':
            print('imported %d employees' % import_employees(store, args.csv))
        elif args.cmd == 'run':
            slips = store.run(_period(args.period), read_inputs(args.inputs))
            print('%-6s %-22s %12s %10s %8s %12s' % ('No', 'Name', 'Gross', 'PAYE', 'UIF', 'Net'))
            for s in slips:
                print('%-6s %-22s %12s %10s %8s %12s' % (s.employee.number, s.employee.name[:22], s.gross, s.paye, s.uif, s.net))
            t = store.summary(_period(args.period))
            print('%-29s %12s %10s %8s %12s' % ('Total (%d)' % t['employees'], t['gross'], t['paye'], t['uif'], t['net']))
        elif args.cmd == 'lock':
            store.lock(_period(args.period))
            print('locked', args.period)
        elif args.cmd == 'payslips':
            from .payslip_pdf import render
            slips = store.payslips(_period(args.period))
            if not slips:
                raise PayrollError('No pay run for %s' % args.period)
            os.makedirs(args.out, exist_ok=True)
            for slip in slips:
                path = os.path.join(args.out, '%s_%s.pdf' % (args.period, slip.employee.number))
                with open(path, 'wb') as f:
                    f.write(render(slip))
                print('wrote', path)
    except PayrollError as e:
        raise SystemExit('error: %s' % e)


if __name__ == '__main__':
    main()
