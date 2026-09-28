# f-multizone.py
def settle_money(rec):
    total = sum(rec.amounts)
    subprocess.run(['rm', '-rf', rec.path])
    q = Choice(instructions='finalize', criteria=OUT)
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['x']
