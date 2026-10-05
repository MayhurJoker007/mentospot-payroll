"""One-page A4 payslip. Needs fpdf2 (pip install fpdf2)."""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

NAVY = (24, 46, 79)
GREY = (110, 110, 110)
RULE = (215, 220, 228)


def _r(amount):
    return 'R ' + format(amount, ',.2f').replace(',', ' ')


def render(slip, company='MentoSpot'):
    e = slip.employee
    pdf = FPDF(format='A4')
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)
    width = pdf.w - 32

    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(*NAVY)
    pdf.cell(width / 2, 10, company)
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(width / 2, 10, 'Payslip  %s' % slip.period.strftime('%B %Y'), align='R',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.6)
    pdf.line(16, pdf.get_y() + 1, 16 + width, pdf.get_y() + 1)
    pdf.ln(5)

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(40, 40, 40)
    masked_id = e.id_number[:6] + '*' * (len(e.id_number) - 6) if e.id_number else '-'
    for label, value in (('Employee', '%s  (%s)' % (e.name, e.number)), ('ID number', masked_id),
                         ('Tax year', str(slip.period.year + (slip.period.month >= 3)))):
        pdf.set_text_color(*GREY)
        pdf.cell(28, 5, label)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 5, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    def block(title, lines, total_label, total):
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(40, 40, 40)
        pdf.set_draw_color(*RULE)
        pdf.set_line_width(0.2)
        for line in lines:
            pdf.cell(16, 6, line.code, border='B')
            pdf.cell(width - 56, 6, line.label, border='B')
            pdf.cell(40, 6, _r(line.amount), border='B', align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if total_label:
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(width - 40, 7, total_label)
            pdf.cell(40, 7, _r(total), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)

    block('Earnings', slip.earnings, 'Gross pay', slip.gross)
    block('Deductions', slip.deductions, 'Total deductions', sum(l.amount for l in slip.deductions))

    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(width - 50, 11, '  Net pay', fill=True)
    pdf.cell(50, 11, _r(slip.net) + '  ', fill=True, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    pdf.set_text_color(40, 40, 40)
    block('Employer contributions (not deducted from your pay)', slip.employer, None, None)

    pdf.set_y(-20)
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, 'Taxable this month: regular %s, irregular %s' % (_r(slip.taxable_regular), _r(slip.taxable_irregular)))
    return bytes(pdf.output())
