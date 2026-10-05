"""Monthly payroll calculation.

Regular pay is taxed on its annual equivalent. Bonuses and other once-off payments are taxed the way SARS
describes for irregular income: the tax on (annual regular income + the bonus) minus the tax on the annual
regular income alone. So a December bonus is taxed in December at the employee's marginal rate, instead of
being annualised as if it were paid every month.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal as D

from .tax_tables import tax_year_for

CENT = D('0.01')


def money(x):
    return D(x).quantize(CENT, rounding=ROUND_HALF_UP)


def age_on(born, on):
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


@dataclass
class Employee:
    number: str
    name: str
    id_number: str
    born: date
    monthly_salary: D
    medical_members: int = 0
    medical_aid_employee: D = D(0)      # deducted from pay
    medical_aid_employer: D = D(0)      # fringe benefit
    pension_employee: D = D(0)
    travel_allowance: D = D(0)
    travel_mostly_business: bool = False
    tax_directive_rate: D | None = None  # fixed rate from a SARS directive, if any


@dataclass
class PeriodInputs:
    """Variable items for one employee in one month."""
    overtime: D = D(0)
    commission: D = D(0)
    bonus: D = D(0)
    unpaid_leave_days: D = D(0)
    working_days: int = 21
    other_deductions: dict = field(default_factory=dict)   # e.g. {"Staff loan": D(500)}


@dataclass
class Line:
    code: str
    label: str
    amount: D


@dataclass
class Payslip:
    employee: Employee
    period: date             # any day in the pay month
    earnings: list
    deductions: list
    employer: list
    gross: D
    taxable_regular: D
    taxable_irregular: D
    paye: D
    uif: D
    net: D

    def total(self, lines, code):
        return sum((l.amount for l in lines if l.code == code), D(0))


class PayrollError(ValueError):
    pass


def calculate(emp, period, inputs=None, employer_pays_sdl=True):
    inputs = inputs or PeriodInputs()
    ty = tax_year_for(period)

    if inputs.unpaid_leave_days < 0 or inputs.unpaid_leave_days > inputs.working_days:
        raise PayrollError('%s: unpaid leave must be between 0 and %d days' % (emp.number, inputs.working_days))

    leave_deduction = money(emp.monthly_salary * inputs.unpaid_leave_days / inputs.working_days)
    basic = emp.monthly_salary - leave_deduction

    earnings = [Line('3601', 'Basic salary', money(emp.monthly_salary))]
    if leave_deduction:
        earnings.append(Line('3601', 'Unpaid leave (%s days)' % inputs.unpaid_leave_days, -leave_deduction))
    for code, label, amount in (('3607', 'Overtime', inputs.overtime),
                                ('3606', 'Commission', inputs.commission),
                                ('3605', 'Bonus', inputs.bonus),
                                ('3701', 'Travel allowance', emp.travel_allowance)):
        if amount:
            earnings.append(Line(code, label, money(amount)))
    gross = sum(l.amount for l in earnings)

    travel_inclusion = D('0.20') if emp.travel_mostly_business else D('0.80')
    regular = basic + inputs.overtime + inputs.commission + emp.travel_allowance * travel_inclusion + emp.medical_aid_employer
    retirement = min(emp.pension_employee,
                     (regular + inputs.bonus) * ty.retirement_percent,
                     ty.retirement_cap / 12)
    taxable_regular = regular - retirement
    taxable_irregular = inputs.bonus

    age = age_on(emp.born, ty.end)
    if emp.tax_directive_rate is not None:
        paye = money((taxable_regular + taxable_irregular) * emp.tax_directive_rate)
    else:
        annual_regular = taxable_regular * 12
        tax_regular = ty.annual_tax(annual_regular, age) / 12
        tax_bonus = ty.annual_tax(annual_regular + taxable_irregular, age) - ty.annual_tax(annual_regular, age)
        credit = ty.monthly_medical_credit(emp.medical_members)
        paye = money(max(D(0), tax_regular + tax_bonus - credit))

    uif_base = min(gross - inputs.commission, ty.uif_monthly_ceiling)
    uif = money(max(D(0), uif_base) * ty.uif_rate)

    deductions = [Line('4102', 'PAYE', paye), Line('4141', 'UIF', uif)]
    if emp.pension_employee:
        deductions.append(Line('4001', 'Pension fund', money(emp.pension_employee)))
    if emp.medical_aid_employee:
        deductions.append(Line('4005', 'Medical aid', money(emp.medical_aid_employee)))
    for label, amount in inputs.other_deductions.items():
        deductions.append(Line('4497', label, money(amount)))

    net = gross - sum(l.amount for l in deductions)
    if net < 0:
        raise PayrollError('%s: deductions (%s) are more than gross pay (%s)' % (
            emp.number, gross - net, gross))

    employer = [Line('4141', 'UIF (employer)', uif)]
    if employer_pays_sdl:
        employer.append(Line('4142', 'SDL', money((regular + taxable_irregular) * ty.sdl_rate)))
    if emp.medical_aid_employer:
        employer.append(Line('3810', 'Medical aid (employer)', money(emp.medical_aid_employer)))

    return Payslip(emp, period, earnings, deductions, employer, gross,
                   money(taxable_regular), money(taxable_irregular), paye, uif, net)
