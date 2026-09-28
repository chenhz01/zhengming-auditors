# f-clean.py
def tag_of(row):
    q = Choice(instructions='route this row', criteria=ROUTES)
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['route']
