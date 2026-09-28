# f-irreversible.py
def refund(path):
    if confirm(path):
        subprocess.run(['rm', '-rf', path])
    q = Choice(instructions='should we refund', criteria=YESNO)
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['ok']
