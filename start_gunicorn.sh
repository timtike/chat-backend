gunicorn --bind 0.0.0.0:8889 --timeout 500 --daemon --reload --access-logfile ./log/access.log --error-logfile ./log/error.log -w 8 app:app > ./log/chatgpt-backend.log 2>&1
