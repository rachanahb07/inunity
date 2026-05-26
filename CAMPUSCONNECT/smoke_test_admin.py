import requests

BASE = 'http://127.0.0.1:5000'

s = requests.Session()
try:
    r = s.post(BASE + '/login', json={'email':'admin@vvce.ac.in','password':'admin123'})
    print('LOGIN', r.status_code, r.text[:1000])

    r = s.get(BASE + '/api/admin/labs')
    print('\nLABS', r.status_code)
    try:
        print(r.json())
    except Exception as e:
        print('Labs JSON parse error', e, r.text[:500])

    r = s.get(BASE + '/api/admin/interactive-classes')
    print('\nINTERACTIVE', r.status_code)
    try:
        print(r.json())
    except Exception as e:
        print('Interactive JSON parse error', e, r.text[:500])

except Exception as e:
    print('ERROR', e)
