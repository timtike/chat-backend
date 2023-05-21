import os
import random
import time
import openai
import boto3
import jwt
from datetime import datetime, timedelta
# import datetime
import logging
import requests

from flask import Flask, jsonify, request
from flask_cors import CORS
from boto3.dynamodb.conditions import Key, Attr


LOG_PATH = "./log/"
LOG_FILE = "chatgpt-backend.log"
if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

# Configure the logging settings
logging.getLogger().setLevel("INFO")
logging.basicConfig(
    filename=LOG_PATH + LOG_FILE,
    filemode="a",
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
    )
# Create a logger object
logger = logging.getLogger()

app = Flask(__name__)

# 配置第一个域名的 CORS
cors_config = {
    "origins": ["*"],
    "methods": ["GET", "POST"],
    "allow_headers": ["Authorization", "Content-Type"]
}
cors = CORS(app, resources={r"*": cors_config})

JWT_SECRET = 'green-town'
# Initialize the OpenAI API client
api_key_list_3 = ['', '']
api_key_list_4 = ['', '', '']

# Initialize the AWS DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
user_table = dynamodb.Table('green-town-chatgpt-stage-user-table')
chatgpt_table = dynamodb.Table('green-town-chatgpt-stage-conversation-table')


def check_jwt(token):
    try:
        # 验证JWT令牌的有效性
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        username = payload['username']
        return username

    except jwt.exceptions.DecodeError:
        # 如果JWT解码错误，返回401 Unauthorized错误
        return {'error': 'Unauthorized'}
    except jwt.exceptions.ExpiredSignatureError:
        # 如果JWT令牌已过期，返回401 Unauthorized错误
        return {'error': 'Token has expired'}


def update_prompt_history(context_id, context_name, context_model, username, conversation, prompt_list, update_time):
    chatgpt_table.put_item(Item={
        'context_id':context_id,
        'context_name':context_name,
        'context_model':context_model,
        'username':username,
        'conversation':conversation,
        'prompt_list':prompt_list,
        'update_time':update_time
    })

def generate_context_name(prompt_list):
    content_list = [prompt['content'] for prompt in prompt_list]
    prompt_string = ','.join(content_list)
    prompt_string = "help me to give me a summary for below context, around 5 words  use chinese to reply\n" + prompt_string

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{'role': 'user', 'content': prompt_string}]
    )
    message = response.choices[0]['message']
    return message['content']

def chat_with_gpt(prompt_list, model):
    # Convert the list of messages into a formatted prompt
    prompt = [{'role': prompt['role'], 'content': prompt['content']} for prompt in prompt_list]
    # Call the ChatGPT API
    invoke_model_name = "gpt-4"
    if 'gpt-3' in model:
        invoke_model_name = 'gpt-3.5-turbo'
        openai.api_key = api_key_list_3[0]
    if 'gpt-4' in model:
        invoke_model_name = 'gpt-4'
        openai.api_key = random.choice(api_key_list_4)

    logger.info(f'model:{model}, key last is: {openai.api_key[-4:]}, last prompt is:{prompt_list[-1]}')
    response = openai.ChatCompletion.create(
        model=invoke_model_name,
        messages=prompt
    )

    # Extract the model's response
    message = response.choices[0]['message']
    logger.info(f'response message from chatgpt: {message}')

    return message

def get_all_conversation_history(username):
    #dynamodb get all item by username
    response = chatgpt_table.scan(
        FilterExpression='username = :val',
        ExpressionAttributeValues={
            ':val': username
        }
    )
    conversation_list = []
    for item in response['Items']:
        conversation_list.append(item)
    print(conversation_list)
    conversation_list = sorted(conversation_list, key=lambda x: x["update_time"], reverse=True)
    print(conversation_list)

    return conversation_list

def get_one_conversation_history(username, context_id):
    # find data in dynamodb with username and context_id
    response = chatgpt_table.get_item(Key={'context_id': context_id})
    conversation= []
    prompt_list = []
    column_data = {}
    if 'Item'in response:
        conversation = response['Item']['conversation']
        prompt_list = response['Item']['prompt_list']
        column_data = response['Item']

    return conversation, prompt_list, column_data

def generate_token(username):
    expiration = datetime.utcnow() + timedelta(days=7)
    payload = {
        'username': username,
        'exp': expiration
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    return token

def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload['username']
    except jwt.exceptions.DecodeError:
        return None
    except jwt.exceptions.ExpiredSignatureError:
        return None

def verify_credentials(username, password):
    response = user_table.query(
        KeyConditionExpression=Key('username').eq(username)
    )
    if len(response['Items']) == 0:
        return False
    user = response['Items'][0]
    return user['password'] == password

@app.route('/login/v1/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')

    password = data.get('pwd')
    if not username or not password:
        return {
        	 "code": -1003,
        	 "msg": "username and pwd must be in body, your body is:{data}",
        	 "data": {}
        }

    response = user_table.query(
        KeyConditionExpression=Key('username').eq(username)
    )
    if len(response['Items']) == 0:
        return {
        	 "code": -1001,
        	 "msg": "user not exist",
        	 "data": {}
        }

    user_info = response['Items'][0]
    if user_info['password'] == password:
        token = generate_token(username)
        return {
        	 "code": 0,
        	 "msg": "login success",
        	 "data": {
        	      "username": username,
        	      "token": token
                }
            }
    else:
        return {
        	 "code": -1002,
        	 "msg": "password is wrong",
        	 "data": {}
        }

@app.route('/chatgpt/v1/prompt', methods=['POST'])
def chatgpt_prompt():
    token = request.headers.get('Authorization')
    username = check_jwt(token)

    data = request.get_json()
    prompts = data['prompt']
    context_id = data['context_id']
    model = data['model']

    conversation, prompt_list,column_data = get_one_conversation_history(username, context_id)

    context_model = column_data.get('model')
    if not context_model:
        context_model = model
    # add question to conversation and prompt list
    for one_prompt in prompts:
        conversation.append({"role": "user", "content": one_prompt})
        prompt_list.append({"role": "user", "content": one_prompt})
    try:
        answer = chat_with_gpt(prompt_list, context_model)
        conversation.append({"role": "assistant", "content": answer['content']})
        code = 0
        msg = 'answer'

    except Exception as e:
        logger.error(f'model: {model},invoke chatgpt api error:{e} ')
        code = -2001
        msg = 'failed to invoke chatgpt'
        answer = ''

    context_name = column_data.get('context_name')
    if not context_name:
        context_name = generate_context_name(prompt_list[:2])

    now = datetime.now()
    update_time = now.strftime("%Y-%m-%d %H:%M:%S")

    update_prompt_history(context_id, context_name, context_model, username, conversation, prompt_list, update_time)

    return {
            "code": code,
            "msg": msg,
            "data": {
                "username": username,
                "answer": answer,
                "context_id": context_id,
                "context_name": context_name,
                "context_model": context_model
            }
    }

@app.route('/chatgpt/v1/all_conversation_history', methods=['GET'])
def chatgpt_all_conversation_history():
    token = request.headers.get('Authorization')
    username = check_jwt(token)

    all_conversation_history = get_all_conversation_history(username)
    return {
            "code": 0,
            "msg": "all conversation history",
            "data": {
                "username": username,
                "conversation_list": all_conversation_history
            }
    }

@app.route('/chatgpt/v1/one_conversation_history', methods=['GET'])
def chatgpt_one_conversation_history():
    token = request.headers.get('Authorization')
    username = check_jwt(token)
    # parse jwt toke
    context_id = request.args.get("context_id", "")
    conversation, prompt_list, column_data = get_one_conversation_history(username, context_id)

    return {
            "code": 0,
            "msg": "one conversation history",
            "data": {
                "username": username,
                "context_id": context_id,
                "conversation": conversation
            }
    }

@app.route('/chatgpt/v1/prompt_doc', methods=['POST'])
def chatgpt_prompt_doc():
    data = request.get_json()
    print(f'body in prompt_doc is:{data}')
    response = requests.get('http://ip-api.com/json/')
    out_ip = response.json()["query"]
    logger.info(f"current out public IP is: {out_ip}")
    return {
            "code": 0,
            "msg": f"current out public IP is: {out_ip}",
            "data": ""
    }

@app.route('/chatgpt/v1/prompt_img', methods=['POST'])
def chatgpt_prompt_img():
    data = request.get_json()
    print(f'body in prompt_doc is:{data}')
    return {
            "code": 0,
            "msg": "prompt img",
            "data": "prompt img"
    }

@app.route('/healthCheck', methods=['GET'])
def chatgpt_healthcheck():
    return "200"

if __name__ == '__main__':
    #app.run()
    app.run(host="0.0.0.0", port="8889", debug=False)
