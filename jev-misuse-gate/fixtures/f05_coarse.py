# f-coarse.py
def score_doc(page_text):
    q = Score(instructions='grade this')
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['grade']
