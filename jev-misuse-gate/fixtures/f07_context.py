# f-context.py
def cleanup(path):
    subprocess.run(['rm', '-rf', path])
    # unrelated step 0, no keyword here
    # unrelated step 1, no keyword here
    # unrelated step 2, no keyword here
    # unrelated step 3, no keyword here
    # unrelated step 4, no keyword here
    # unrelated step 5, no keyword here
    # unrelated step 6, no keyword here
    # unrelated step 7, no keyword here
    # unrelated step 8, no keyword here
    # unrelated step 9, no keyword here
    # unrelated step 10, no keyword here
    # unrelated step 11, no keyword here
    # unrelated step 12, no keyword here
    # unrelated step 13, no keyword here
    # unrelated step 14, no keyword here
    # unrelated step 15, no keyword here
def decide(row):
    q = Choice(instructions='pick bucket', criteria=BUCKETS)
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['b']
