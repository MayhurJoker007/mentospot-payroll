# MentoSpot Payroll

Monthly South African payroll for MentoSpot, in Python: PAYE, UIF, SDL, medical tax credits, retirement fund
deductions, pay runs that lock once they're final, and PDF payslips.

The core has no dependencies beyond the standard library. All money is `Decimal`, rounded to the cent once,
at the end.

```
python -m mentospot_payroll import samples/employees.csv
python -m mentospot_payroll run 2025-12 --inputs samples/inputs-2025-12.csv
```

```
No     Name                          Gross       PAYE      UIF          Net
M001   Naledi Khumalo             32000.00    4352.33   177.12     22970.55
M002   Pieter Botha               22750.00    2742.08   177.12     19830.80
M003   Ayanda Mthembu              9333.33     243.75    93.33      8996.25
Total (3)                         64083.33    7338.16   447.57     51797.60
```

```
python -m mentospot_payroll lock 2025-12
python -m mentospot_payroll payslips 2025-12 --out payslips/
```

There's an example payslip in [samples/payslip-example.pdf](samples/payslip-example.pdf).

## How tax is calculated

**Regular pay** (salary, overtime, commission, the taxable part of the travel allowance, and the employer's medical
aid contribution as a fringe benefit, less pension contributions) is annualised, put through the brackets with the
age-based rebates, and divided by 12. Medical credits come off after that.

**Bonuses** are taxed the way SARS treats irregular income: tax on (annual regular income + bonus) minus tax on
the annual regular income. So a R30 000 December bonus on a R30 000 salary costs R8 775 in tax that month, which is
exactly the extra tax it adds for the year. Annualising the whole December payslip instead would overstate the tax badly.

**Tax directives** replace the table calculation with the directive's fixed rate.

**UIF** is 1% each from employee and employer, on pay excluding commission, capped at the monthly ceiling.
**SDL** is 1% for the employer.

Rates live in `tax_tables.py`, one entry per tax year. 2026 (March 2025 to February 2026) is included.

## Pay runs

- `run` calculates a **draft** for every active employee. Drafts can be recalculated as many times as needed,
  for example when overtime figures come in late.
- `lock` freezes the run. After that it can't be recalculated.
- Each payslip stores a **snapshot of the employee record** as it was at the time, so a salary change in
  February doesn't quietly rewrite December's payslip when it's reprinted.
- Variable inputs for an employee who doesn't exist or isn't active are rejected, rather than silently dropped.
- A payslip where deductions exceed gross pay is an error, not a negative net.
- `year_to_date()` totals each IRP5 source code from March up to any month.

## Tests

```
pip install -e .[test]
pytest
```

18 tests. Each expected figure was worked out by hand from the SARS tables, and the arithmetic is in the
test comments.

## Not covered (yet)

Weekly or fortnightly pay, mid-month starters and leavers, ETI, and the EMP201/EMP501 submissions themselves.
