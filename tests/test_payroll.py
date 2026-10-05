from datetime import date
from decimal import Decimal as D

import pytest

from mentospot_payroll import Employee, PayrollError, PayrollStore, PeriodInputs, calculate
from mentospot_payroll.tax_tables import TAX_YEARS, tax_year_for

MARCH = date(2025, 3, 1)
DECEMBER = date(2025, 12, 1)


def emp(**kw):
    base = dict(number='M001', name='Naledi Khumalo', id_number='9504120123087', born=date(1995, 4, 12),
                monthly_salary=D(30000))
    base.update(kw)
    return Employee(**base)


def paye(slip):
    return slip.total(slip.deductions, '4102')


def test_monthly_paye_is_annual_tax_over_twelve():
    # 360 000 a year: 42 678 + 26% x 122 900 - 17 235 = 57 397
    assert paye(calculate(emp(), MARCH)) == D('4783.08')


def test_bonus_taxed_at_marginal_rate_in_the_month_paid():
    slip = calculate(emp(), DECEMBER, PeriodInputs(bonus=D(30000)))
    # tax on 390 000 (66 172) less tax on 360 000 (57 397) = 8 775, on top of the normal month
    assert paye(slip) == D('4783.08') + D(8775)
    assert slip.taxable_irregular == D(30000)


def test_below_threshold_pays_nothing():
    assert paye(calculate(emp(monthly_salary=D(7500)), MARCH)) == 0


def test_pensioner_rebates():
    older = emp(born=date(1950, 1, 1), monthly_salary=D(14000))   # 76 at year end
    # 168 000 x 18% = 30 240, less 17 235 + 9 444 + 3 145 = 416, / 12
    assert paye(calculate(older, MARCH)) == D('34.67')


def test_medical_credits_and_pension():
    slip = calculate(emp(medical_members=3, pension_employee=D(2400), medical_aid_employee=D(3100)), MARCH)
    assert slip.taxable_regular == D(27600)
    # 331 200: 42 678 + 26% x 94 100 - 17 235 = 49 909 / 12 = 4159.08, less 364 + 364 + 246
    assert paye(slip) == D('3185.08')
    assert slip.net == slip.gross - sum(l.amount for l in slip.deductions)


def test_unpaid_leave_is_pro_rata():
    slip = calculate(emp(monthly_salary=D(21000)), MARCH, PeriodInputs(unpaid_leave_days=D(2), working_days=21))
    assert slip.gross == D(19000)


def test_uif_ceiling_and_commission_exclusion():
    slip = calculate(emp(monthly_salary=D(12000)), MARCH, PeriodInputs(commission=D(9000)))
    assert slip.uif == D('120.00')
    assert calculate(emp(monthly_salary=D(50000)), MARCH).uif == D('177.12')


def test_tax_directive_overrides_the_tables():
    slip = calculate(emp(monthly_salary=D(20000), tax_directive_rate=D('0.25')), MARCH)
    assert paye(slip) == D(5000)


def test_deductions_cannot_exceed_pay():
    with pytest.raises(PayrollError, match='more than gross'):
        calculate(emp(monthly_salary=D(5000)), MARCH, PeriodInputs(other_deductions={'Staff loan': D(6000)}))


def test_unknown_tax_year():
    with pytest.raises(ValueError, match='2031'):
        tax_year_for(date(2030, 6, 1))


@pytest.mark.parametrize('income, expected', [(237100, 25443), (500000, 100272), (2000000, 709604)])
def test_bracket_edges(income, expected):
    assert TAX_YEARS[2026].annual_tax(D(income), 40) == expected


# --- pay runs --------------------------------------------------------------

@pytest.fixture
def store():
    s = PayrollStore()
    s.save_employee(emp())
    s.save_employee(emp(number='M002', name='Pieter Botha', id_number='8811035009081', born=date(1988, 11, 3),
                        monthly_salary=D(18500), travel_allowance=D(3000)))
    return s


def test_run_lock_and_no_recalculation_after_lock(store):
    store.run(MARCH)
    store.run(MARCH, {'M002': PeriodInputs(overtime=D(1200))})   # drafts can be redone
    store.lock(MARCH)
    with pytest.raises(PayrollError, match='locked'):
        store.run(MARCH)
    assert store.summary(MARCH)['employees'] == 2


def test_stored_payslips_match_what_was_calculated(store):
    calculated = {s.employee.number: s for s in store.run(MARCH)}
    store.save_employee(emp(monthly_salary=D(99999)))   # a later change mustn't rewrite history
    for stored in store.payslips(MARCH):
        assert stored.net == calculated[stored.employee.number].net
        assert stored.employee.monthly_salary != D(99999)


def test_inputs_for_unknown_employee_are_rejected(store):
    with pytest.raises(PayrollError, match='M999'):
        store.run(MARCH, {'M999': PeriodInputs(bonus=D(1))})


def test_year_to_date_by_source_code(store):
    store.run(date(2025, 3, 1))
    store.run(date(2025, 4, 1))
    store.run(date(2026, 2, 1))  # after the period asked for, excluded
    ytd = store.year_to_date('M001', date(2025, 4, 1))
    assert ytd['3601'] == D(60000)
    assert ytd['4102'] == D('9566.16')


def test_payslip_pdf(store):
    pytest.importorskip('fpdf')
    from mentospot_payroll.payslip_pdf import render
    slip = store.run(MARCH)[0]
    pdf = render(slip)
    assert pdf[:5] == b'%PDF-'
