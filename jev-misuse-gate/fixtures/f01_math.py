# f-math.py
def invoice_check(doc):
    total = sum(l.amount for l in doc.lines)
    assert abs(total - doc.invoice_total) < 0.01
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['match']
