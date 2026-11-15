import base64
import os
from dotenv import load_dotenv
import uuid
import time
import hmac
import hashlib
import requests

import ui

load_dotenv()

def create_header():
    token = os.getenv('SWITCHBOT_TOKEN')
    secret = os.getenv('SWITCHBOT_SECRET')
    nonce = uuid.uuid4()
    timestamp = int(round(time.time() * 1000))
    string_to_sign = f'{token}{timestamp}{nonce}'
    signature = base64.b64encode(hmac.new(secret.encode(), msg=string_to_sign.encode(), digestmod=hashlib.sha256).digest()).decode()
    return {
        'Authorization': token,
        'Content-Type': 'application/json',
        'charset': 'utf8',
        't': str(timestamp),
        'sign': signature,
        'nonce': str(nonce)
    }

def get_devices(header):
    url = 'https://api.switch-bot.com/v1.1/devices'
    response = requests.get(url, headers=header)
    if response.status_code == 200:
        return response.json()
    else:
        return f"Error: {response.status_code}, {response.json()}"

def control_light(command): #command: 'turnOn' or 'turnOff'
    if command == 'turnOff':
        ui.set_light_off()
        print("ライトを消しました")
    # header = create_header()
    # devices = get_devices(header)
    # deviceList = devices['body']['infraredRemoteList']
    # for device in deviceList:
    #     if device['deviceName'] == 'ライト':
    #         url = f'https://api.switch-bot.com/v1.1/devices/{device['deviceId']}/commands'
    #         payload = {
    #             'command': command,
    #             'parameter': 'default'
    #         }
    #         response = requests.post(url, headers=header, json=payload)
    #         if response.status_code == 200:
    #             print(response.json())
    #         else:
    #             print(f"Error: {response.status_code}, {response.json()}")