# f-chinese.py
def classify_cn(msg):
    state = {'customer_message': msg}
    q = Choice(instructions='判断 customer_message 属于哪一类客户消息')
    resp = client.system_one(state=state, questions=questions)  # Jev call

    return resp.answers['kind']
