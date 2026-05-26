import os
old = 'flask_session'
new = 'flask_session_files'
if os.path.isdir(old) and not os.path.isdir(new):
    os.rename(old, new)
    print('Renamed', old, '->', new)
else:
    print('No rename performed; source missing or target exists')
