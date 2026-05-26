import requests, base64, os
BASE='http://127.0.0.1:5000'
# 1. Register teacher
reg = requests.post(BASE+'/register', json={
    'email':'teach1@vvce.ac.in',
    'password':'teach123',
    'confirm_password':'teach123',
    'full_name':'Teacher One',
    'role':'teacher'
})
print('REGISTER', reg.status_code, reg.text[:400])
# 2. Admin login
s = requests.Session()
login = s.post(BASE+'/login', json={'email':'admin@vvce.ac.in','password':'admin123'})
print('ADMIN LOGIN', login.status_code, login.text[:200])
# 3. Get users and find teacher id
users = s.get(BASE+'/api/admin/users').json()
teacher = next((u for u in users if u['email']=='teach1@vvce.ac.in'), None)
print('FOUND TEACHER', teacher)
if not teacher:
    raise SystemExit('Teacher not found')
teacher_id = teacher['id']
# 4. Create small PNG file
png_data = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=')
fpath = 'temp_photo.png'
with open(fpath,'wb') as f: f.write(png_data)
# 5. Upload photo as admin
with open(fpath,'rb') as f:
    r = s.post(BASE+f'/api/admin/teacher/{teacher_id}/upload-photo', files={'photo': f})
print('UPLOAD', r.status_code, r.text[:400])
# 6. Login as teacher and fetch profile
s2 = requests.Session()
login2 = s2.post(BASE+'/login', json={'email':'teach1@vvce.ac.in','password':'teach123'})
print('TEACH LOGIN', login2.status_code, login2.text[:200])
profile = s2.get(BASE+'/api/teacher/profile').json()
print('PROFILE', profile)
# cleanup
try:
    os.remove(fpath)
except:
    pass
