import requests
BASE='http://127.0.0.1:5000'

s = requests.Session()
login = s.post(BASE+'/login', json={'email':'admin@vvce.ac.in','password':'admin123'})
print('LOGIN', login.status_code)
resp = s.get(BASE+'/api/admin/export-logs')
print('EXPORT', resp.status_code)
print('Headers:', resp.headers.get('Content-Type'), resp.headers.get('Content-Disposition'))
print('Sample:\n', resp.text[:500])
