# -*- coding: utf-8 -*-
"""Read a bank statement PDF into rows, and prove the rows are right.

No bank publishes its PDF layout, and every bank's differs: columns move, a
value date sits beside the booking date, debit and credit share a column or
not. What they all print is a running balance. So the reader does not try to
know the layout; it rebuilds the lines from where each word sits on the page,
takes the date at the start of a line and the figures at its end, and lets
the balance say which way the money went.

Then it checks itself. Every row's amount must equal the change in balance
from the row before, and opening plus all rows must equal the closing balance
the bank printed. A statement that fails either is refused, naming the row —
a reader that guesses a figure is worse than one that stops, because the
guessed figure gets reconciled and nobody looks at it again.

Pure functions, no Odoo: tested on their own (tests/test_pdf_statement.py).
"""
import io
import re
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

DATE_RE = re.compile(
    r"^(?P<d>\d{1,2})[/\-. ](?P<m>\d{1,2}|[A-Za-z]{3})[/\-. ](?P<y>\d{2,4})\b")
AMOUNT_RE = re.compile(r"^\(?-?[\d,]+\.\d{2}\)?(?:\s?(?:CR|DR|Cr|Dr))?$")
IBAN_RE = re.compile(r"\b(AE\d{2}(?:\s?\d{3,4}){4,6})\b")
ACCOUNT_RE = re.compile(r"(?:Account\s*(?:No\.?|Number)|رقم الحساب)\s*[:#]?\s*([\d\- ]{8,24})", re.I)
CURRENCY_RE = re.compile(r"(?:Currency|العملة)\s*[:]?\s*([A-Z]{3})\b|\b(AED|USD|EUR|SAR|GBP)\b")
OPENING_RE = re.compile(r"(opening|brought forward|balance b/f|previous balance|الرصيد الافتتاحي|رصيد سابق)", re.I)
# Repeated page furniture on long statements, never part of a description.
HEADER_RE = re.compile(r"(^page\s+\d|\bpage \d+ of \d+|^date\b.*\bbalance\b|^statement\b|"
                       r"^account (name|no|number)|continued|التاريخ.*الرصيد)", re.I)
CLOSING_RE = re.compile(r"(closing|carried forward|balance c/f|ending balance|الرصيد الختامي)", re.I)


class StatementError(ValueError):
    """The PDF was read but its figures do not add up, or nothing was found."""


# ----------------------------------------------------------------- lines
def pdf_lines(data):
    """Text lines of every page, rebuilt from word positions, top to bottom.

    pdfminer returns text boxes in whatever order the PDF drew them, which
    for a table is often column by column. Grouping every text line by its
    vertical position puts each table row back together, left to right."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextContainer, LTTextLine

    out = []
    params = LAParams(line_margin=0.2, char_margin=1.5, word_margin=0.1)
    for page in extract_pages(io.BytesIO(data), laparams=params):
        pieces = []

        def walk(obj):
            if isinstance(obj, LTTextLine):
                text = obj.get_text().strip()
                if text:
                    pieces.append((round(obj.y1, 0), obj.x0, text))
            elif isinstance(obj, LTTextContainer) or hasattr(obj, "__iter__"):
                for child in obj:
                    walk(child)

        walk(page)
        rows = []
        for y, x, text in sorted(pieces, key=lambda p: (-p[0], p[1])):
            if rows and abs(rows[-1][0] - y) <= 3:
                rows[-1][1].append((x, text))
            else:
                rows.append([y, [(x, text)]])
        for _y, cells in rows:
            out.append([t for _x, t in sorted(cells)])
    return out


# ----------------------------------------------------------------- values
def parse_amount(text):
    t = text.strip().replace(" ", "")
    negative = t.startswith("(") or t.startswith("-") or t.upper().endswith("DR")
    t = re.sub(r"(?i)(CR|DR)$", "", t).strip("()-")
    value = float(t.replace(",", ""))
    return -value if negative else value


def parse_date(text):
    m = DATE_RE.match(text.strip())
    if not m:
        return None
    d, mo, y = m.group("d"), m.group("m"), m.group("y")
    month = MONTHS.get(mo[:3].lower()) if mo.isalpha() else int(mo)
    year = int(y) + (2000 if len(y) == 2 else 0)
    try:
        return date(year, month, int(d))
    except (TypeError, ValueError):
        return None


def _split_row(cells):
    """(date, description, [amounts]) from a row's cells, or None."""
    text = "  ".join(cells)
    first = parse_date(text)
    if not first:
        return None
    rest = DATE_RE.sub("", text, count=1).strip()
    # a value date printed beside the booking date
    if parse_date(rest):
        rest = DATE_RE.sub("", rest, count=1).strip()
    tokens = re.split(r"\s{2,}|\t", rest)
    tokens = [t for t in (tok.strip() for tok in tokens) if t]
    amounts = []
    while tokens and AMOUNT_RE.match(tokens[-1].replace(" ", "")):
        amounts.insert(0, parse_amount(tokens.pop()))
    # a description that itself ends in a figure glued to the amounts
    words = " ".join(tokens).split(" ")
    while len(amounts) < 2 and words and AMOUNT_RE.match(words[-1]):
        amounts.insert(0, parse_amount(words.pop()))
    description = " ".join(w for w in words if w).strip()
    return first, description, amounts


# ----------------------------------------------------------------- statement
def parse_statement(data):
    """Return a dict: currency, account_number, balance_start, balance_end,
    transactions [{date, payment_ref, amount, balance}] — or raise
    StatementError explaining exactly what did not add up."""
    lines = pdf_lines(data)
    if not lines:
        raise StatementError("The PDF has no text in it. A scanned statement cannot be read; "
                             "download the statement from online banking instead.")
    flat = ["  ".join(cells) for cells in lines]
    whole = "\n".join(flat)

    iban = IBAN_RE.search(whole)
    account = re.sub(r"\s", "", iban.group(1)) if iban else None
    if not account:
        m = ACCOUNT_RE.search(whole)
        account = re.sub(r"[\s\-]", "", m.group(1)) if m else None
    m = CURRENCY_RE.search(whole)
    currency = (m.group(1) or m.group(2)) if m else "AED"

    opening = closing = None
    rows = []
    pending = []          # text lines with no date and no figure: a wrapped description
    started = ended = False
    for cells, text in zip(lines, flat):
        split = _split_row(cells)
        if split and split[2]:
            day, description, amounts = split
            if OPENING_RE.search(description) and opening is None:
                opening = amounts[-1]
                started, pending = True, []
                continue
            if CLOSING_RE.search(description):
                closing = amounts[-1]
                if rows and pending:
                    rows[-1]["description"] = (rows[-1]["description"] + " " + " ".join(pending)).strip()
                ended, pending = True, []
                continue
            if not description and pending:
                # the cell wrapped and the text sits above the figures
                description = " ".join(pending)
            elif pending and rows:
                # the cell wrapped below the previous row's figures
                rows[-1]["description"] = (rows[-1]["description"] + " " + " ".join(pending)).strip()
            pending = []
            rows.append({"date": day, "description": description, "amounts": amounts, "text": text})
            started = True
            continue
        if OPENING_RE.search(text) and opening is None:
            figures = [parse_amount(t) for t in re.findall(r"\(?-?[\d,]+\.\d{2}\)?", text)]
            if figures:
                opening = figures[-1]
                started, pending = True, []
            continue
        if CLOSING_RE.search(text):
            figures = [parse_amount(t) for t in re.findall(r"\(?-?[\d,]+\.\d{2}\)?", text)]
            if figures:
                closing = figures[-1]
                ended, pending = True, []
            continue
        if started and not ended and not HEADER_RE.search(text) \
                and not re.search(r"[\d,]+\.\d{2}", text):
            pending.append(text.replace("  ", " ").strip())
    if rows and pending and not ended:
        rows[-1]["description"] = (rows[-1]["description"] + " " + " ".join(pending)).strip()

    if not rows:
        raise StatementError("No transaction rows were found: no line starts with a date and ends with a balance.")
    rows = [r for r in rows if len(r["amounts"]) >= 2]
    if not rows:
        raise StatementError("Transaction rows were found but none shows a running balance, "
                             "so the direction of each amount cannot be proven.")

    if opening is None:
        first = rows[0]
        # without a printed opening balance, the first row's own balance and
        # amount still give it: balance before = balance after ∓ amount
        a, bal = first["amounts"][-2], first["amounts"][-1]
        opening = round(bal - a, 2) if len(first["amounts"]) == 2 else None
        if opening is None:
            raise StatementError("The statement prints no opening balance.")

    transactions, previous = [], round(opening, 2)
    for number, row in enumerate(rows, 1):
        balance = round(row["amounts"][-1], 2)
        moved = round(balance - previous, 2)
        listed = [abs(round(a, 2)) for a in row["amounts"][:-1] if round(a, 2)]
        if abs(moved) not in listed:
            raise StatementError(
                "Row %d (%s, %s) does not add up: the balance moved by %.2f but the row shows %s. "
                "Nothing was imported." % (number, row["date"].strftime("%d/%m/%Y"),
                                          row["description"][:60] or "-", moved,
                                          ", ".join("%.2f" % a for a in listed) or "no amount"))
        transactions.append({"date": row["date"], "payment_ref": row["description"] or "-",
                             "amount": moved, "balance": balance})
        previous = balance

    if closing is not None and round(closing, 2) != previous:
        raise StatementError(
            "The rows end at %.2f but the bank prints a closing balance of %.2f: "
            "a row is missing or unreadable. Nothing was imported." % (previous, closing))

    return {
        "currency": currency,
        "account_number": account,
        "balance_start": round(opening, 2),
        "balance_end": previous,
        "closing_printed": closing is not None,
        "transactions": transactions,
    }
