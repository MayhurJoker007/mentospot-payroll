"""SARS rates per tax year. A tax year runs 1 March to the end of February and is named after the year it ends in."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal as D


@dataclass(frozen=True)
class TaxYear:
    year: int
    brackets: tuple          # (threshold, base tax, marginal rate)
    primary_rebate: D
    secondary_rebate: D      # 65 and older
    tertiary_rebate: D       # 75 and older
    medical_credit_main: D   # per month, main member and first dependant each
    medical_credit_extra: D  # per month, each additional dependant
    uif_rate: D
    uif_monthly_ceiling: D
    sdl_rate: D
    retirement_percent: D
    retirement_cap: D

    @property
    def end(self):
        return date(self.year, 2, 28) if self.year % 4 else date(self.year, 2, 29)

    def annual_tax(self, taxable, age):
        """Tax on an annual amount after rebates, before medical credits."""
        if taxable <= 0:
            return D(0)
        threshold, base, rate = next(b for b in reversed(self.brackets) if taxable > b[0] or b[0] == 0)
        tax = base + (taxable - threshold) * rate
        rebate = self.primary_rebate
        if age >= 65:
            rebate += self.secondary_rebate
        if age >= 75:
            rebate += self.tertiary_rebate
        return max(D(0), tax - rebate)

    def monthly_medical_credit(self, members):
        if members <= 0:
            return D(0)
        return min(members, 2) * self.medical_credit_main + max(0, members - 2) * self.medical_credit_extra


TAX_YEARS = {
    2026: TaxYear(
        year=2026,
        brackets=(
            (D(0), D(0), D('0.18')),
            (D(237100), D(42678), D('0.26')),
            (D(370500), D(77362), D('0.31')),
            (D(512800), D(121475), D('0.36')),
            (D(673000), D(179147), D('0.39')),
            (D(857900), D(251258), D('0.41')),
            (D(1817000), D(644489), D('0.45')),
        ),
        primary_rebate=D(17235),
        secondary_rebate=D(9444),
        tertiary_rebate=D(3145),
        medical_credit_main=D(364),
        medical_credit_extra=D(246),
        uif_rate=D('0.01'),
        uif_monthly_ceiling=D(17712),
        sdl_rate=D('0.01'),
        retirement_percent=D('0.275'),
        retirement_cap=D(350000),
    ),
}


def tax_year_for(d):
    year = d.year + 1 if d.month >= 3 else d.year
    try:
        return TAX_YEARS[year]
    except KeyError:
        raise ValueError('No tax tables for the %d tax year' % year) from None
