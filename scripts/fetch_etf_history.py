from mootdx.quotes import Quotes

client = Quotes.factory(market='standard')

etfs = [
    ('510300', 1),
    ('588000', 1),
    ('159915', 0),
    ('512480', 1),
]

costs = {'510300': 4.670, '588000': 1.834, '159915': 3.513, '512480': 1.056}

target_dates = ['2026-07-21', '2026-07-25', '2026-07-28', '2026-07-29',
                '2026-07-30', '2026-07-31', '2026-08-01', '2026-08-03']

for code, market in etfs:
    klines = client.bars(symbol=code, frequency=9, offset=0, market=market, count=25)
    print(f'\n=== {code} (cost {costs[code]}) ===')
    if klines is not None and len(klines) > 0:
        for _, row in klines.iterrows():
            date_str = str(row.get('datetime', ''))[:10] if 'datetime' in row else str(row.get('date', ''))[:10]
            if date_str in target_dates:
                o = round(float(row.get('open', 0)), 3)
                h = round(float(row.get('high', 0)), 3)
                lo = round(float(row.get('low', 0)), 3)
                c = round(float(row.get('close', 0)), 3)
                loss_vs_cost = round((c - costs[code]) / costs[code] * 100, 2)
                print(f'  {date_str} O:{o} H:{h} L:{lo} C:{c} | vs_cost {loss_vs_cost:+.2f}%')
    else:
        print('  No data')
