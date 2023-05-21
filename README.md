# chat-backend

### How to deploy

1.add your key

2.install requirements
python3 -m pip install -r requirements.txt

3.bash start_gunicorn.sh

you can configure worker count in start_gunicorn.sh
-w 8 means 8 workers
workers = cpu count*2

