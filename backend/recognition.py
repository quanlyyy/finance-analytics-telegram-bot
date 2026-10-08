"""Conservative amount extraction; ambiguous values need manual confirmation."""
import re
from datetime import date
from decimal import Decimal
from .finance import parse_expense

NUMBERS = dict(zip('один одна два две три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать семнадцать восемнадцать девятнадцать двадцать тридцать сорок пятьдесят шестьдесят семьдесят восемьдесят девяносто сто двести триста четыреста пятьсот шестьсот семьсот восемьсот девятьсот'.split(), [1,1,2,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,30,40,50,60,70,80,90,100,200,300,400,500,600,700,800,900]))

def spoken_numbers(text):
    tokens = re.findall(r'\w+|[^\w\s]', text.lower())
    out, value, active = [], 0, False
    for token in tokens + ['']:
        if token in NUMBERS:
            value += NUMBERS[token]; active = True
        elif token in ('тысяча','тысячи','тысяч'):
            value = (value or 1) * 1000; active = True
        else:
            if active:
                out.append(str(value)); value, active = 0, False
            out.append(token)
    return ' '.join(out).strip()

def preview(text, kind):
    result = dict(amount=None, kind='expense', category='Другое', note=text[:300], date=date.today().isoformat())
    if kind == 'receipt':
        totals = re.findall(r'(?im)^\s*(?:итого?|к\s+оплате|сумма\s+чека)\s*[:=]?\s*(\d[\d ]*(?:[.,]\d{2})?)\s*(?:₽|руб\.?|р\.?)?\s*$', text)
        values = {int(Decimal(v.replace(' ','').replace(',','.')) * 100) for v in totals}
        if len(values) == 1:
            result['amount'] = values.pop()
        result['note'] = 'Чек: ' + text.splitlines()[0][:290] if text.strip() else 'Чек'
        result['category'] = parse_expense(text.replace('\n',' ')[:250] + ' 1').category
    else:
        normalized = spoken_numbers(text)
        amounts = re.findall(r'(\d+(?:\s*[.,]\s*\d{1,2})?)\s*(?:руб\w*|₽)(?:\s+(\d+)\s*коп\w*)?', normalized)
        if len(amounts) == 1 and len(re.findall(r'\d+(?:\s*[.,]\s*\d+)?', normalized)) == (2 if amounts[0][1] else 1):
            rub, kop = amounts[0]
            if not kop or int(kop) < 100:
                result['amount'] = int(Decimal(re.sub(r'\s','',rub).replace(',','.')) * 100) + int(kop or 0)
        elif not amounts:
            numbers = re.findall(r'\d+(?:\s*[.,]\s*\d{1,2})?', normalized)
            if len(numbers) == 1:
                result['amount'] = int(Decimal(re.sub(r'\s','',numbers[0]).replace(',','.')) * 100)
        parsed = parse_expense(text.replace('\n',' ')[:250] + ' 1')
        result.update(category=parsed.category, kind=parsed.kind)
    if result['amount'] is not None and not 0 < result['amount'] <= 100_000_000_000:
        result['amount'] = None
    return dict(text=text[:6000], entry=result)
