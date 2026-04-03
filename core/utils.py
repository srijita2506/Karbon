from decimal import Decimal, ROUND_DOWN

ROUNDING = Decimal('0.01')


def _quantize(value):
    return value.quantize(ROUNDING, rounding=ROUND_DOWN)


def compute_shares(total, mode, splits):
    if total is None:
        raise ValueError('Total amount required.')
    total = Decimal(total)
    if not splits:
        raise ValueError('At least one participant is required.')

    if mode == 'equal':
        count = len(splits)
        per = _quantize(total / Decimal(count))
        shares = [per for _ in range(count)]
        if count > 1:
            shares[-1] = total - sum(shares[:-1])
        return shares

    if mode == 'amount':
        amounts = []
        for split in splits:
            amount = split.get('amount')
            if amount is None:
                raise ValueError('Amount is required for custom amount splits.')
            amounts.append(Decimal(amount))
        amounts = [_quantize(a) for a in amounts]
        diff = total - sum(amounts)
        if amounts:
            amounts[-1] = _quantize(amounts[-1] + diff)
        return amounts

    if mode == 'percent':
        percents = []
        for split in splits:
            percent = split.get('percentage')
            if percent is None:
                raise ValueError('Percentage is required for percent splits.')
            percents.append(Decimal(percent))
        total_percent = sum(percents)
        if total_percent == 0:
            raise ValueError('Total percentage must be greater than 0.')
        amounts = []
        for percent in percents:
            share = total * (percent / total_percent)
            amounts.append(_quantize(share))
        if len(amounts) > 1:
            amounts[-1] = total - sum(amounts[:-1])
        return amounts

    raise ValueError('Invalid split mode.')


def compute_balances(expenses):
    balances = {}
    for expense in expenses:
        payer_id = expense.payer_id
        balances.setdefault(payer_id, Decimal('0.00'))
        balances[payer_id] += Decimal(expense.amount)

        splits = list(expense.splits.all())
        split_payload = []
        for split in splits:
            split_payload.append(
                {
                    'participant_id': split.participant_id,
                    'amount': split.amount,
                    'percentage': split.percentage,
                }
            )

        shares = compute_shares(Decimal(expense.amount), expense.split_mode, split_payload)
        for split, share in zip(split_payload, shares):
            pid = split['participant_id']
            balances.setdefault(pid, Decimal('0.00'))
            balances[pid] -= Decimal(share)

    return balances


def compute_settlements(balances):
    creditors = []
    debtors = []
    for participant_id, balance in balances.items():
        balance = _quantize(Decimal(balance))
        if balance > 0:
            creditors.append([participant_id, balance])
        elif balance < 0:
            debtors.append([participant_id, -balance])

    settlements = []
    i = 0
    j = 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debt = debtors[i]
        creditor_id, credit = creditors[j]
        amount = debt if debt <= credit else credit
        amount = _quantize(amount)
        if amount > 0:
            settlements.append(
                {
                    'from_participant_id': debtor_id,
                    'to_participant_id': creditor_id,
                    'amount': amount,
                }
            )
        debt -= amount
        credit -= amount
        debtors[i][1] = debt
        creditors[j][1] = credit
        if debt <= 0:
            i += 1
        if credit <= 0:
            j += 1

    return settlements


def compute_contributions(expenses):
    totals = {}
    for expense in expenses:
        payer_id = expense.payer_id
        totals.setdefault(payer_id, {'paid': Decimal('0.00'), 'share': Decimal('0.00')})
        totals[payer_id]['paid'] += Decimal(expense.amount)

        splits = list(expense.splits.all())
        split_payload = []
        for split in splits:
            split_payload.append(
                {
                    'participant_id': split.participant_id,
                    'amount': split.amount,
                    'percentage': split.percentage,
                }
            )

        shares = compute_shares(Decimal(expense.amount), expense.split_mode, split_payload)
        for split, share in zip(split_payload, shares):
            pid = split['participant_id']
            totals.setdefault(pid, {'paid': Decimal('0.00'), 'share': Decimal('0.00')})
            totals[pid]['share'] += Decimal(share)

    for payload in totals.values():
        payload['paid'] = _quantize(payload['paid'])
        payload['share'] = _quantize(payload['share'])

    return totals
