from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
from datetime import datetime
import threading
import time
from functools import wraps

# Global Configuration
CONFIG = {
    'MN_CSE_HOST': 'localhost',
    'MN_CSE_PORT': '3000',
    'IN_CSE_HOST': 'localhost',
    'IN_CSE_PORT': '8080',
    'LOCAL_HOST': '192.168.0.8',
    'LOCAL_PORT': '5000',
    'AE_ID': 'ID-IN',
    'AUTH_TOKEN': 'your_secret_token_here',  # 실제 토큰으로 교체 필요
    'MN_ORIGINATOR': 'CAdmin'  # MN-CSE Originator
}

# URLs
MN_CSE_URL = f"https://{CONFIG['MN_CSE_HOST']}:{CONFIG['MN_CSE_PORT']}/id-in"
IN_CSE_URL = f"https://{CONFIG['IN_CSE_HOST']}:{CONFIG['IN_CSE_PORT']}/id-in"
NOTIFICATION_URL = f"http://{CONFIG['LOCAL_HOST']}:{CONFIG['LOCAL_PORT']}/notifi"

app = Flask(__name__)
CORS(app)

# Token Authentication Decorator
def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization token"}), 401
        
        token = auth_header.split('Bearer ')[1]
        if token != CONFIG['AUTH_TOKEN']:
            return jsonify({"error": "Invalid token"}), 401
            
        return f(*args, **kwargs)
    return decorated_function

def create_headers(originator: str, resource_type: str = None, request_id: str = None, time: str = None, rsc: str = None) -> dict:
    headers = {
        "Accept": "application/json;",
        "X-M2M-Origin": originator,
        "X-M2M-RVI": "2a",
        "Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}"
    }

    if rsc:
        headers["X-M2M-RSC"] = rsc

    if resource_type:
        headers["Content-Type"] = 'application/json;ty=' + resource_type

    if request_id:
        headers["X-M2M-RI"] = request_id

    if time:
        headers["'X-M2M-OT'"] = time

    return headers

def create_container(ae_url, sensor, ae_ri):
    header = create_headers(ae_ri, '3', 'creat_cnt')
    container_payload = {
        "m2m:cnt": {
            "rn": sensor
            "con": {
                "power": "" #on/off
                "lux": "" #밝기
                "rgb": "rgb" #색상
            }
        }
    }

    response = requests.post(ae_url, headers=header, json=container_payload, verify=False)
    if response.status_code == 201:
        print(f"Container '{sensor}' created successfully under AE {ae_url}")
    else:
        print(f"Failed to create container '{sensor}': {response.status_code} {response.text}")

def create_timeseries(ae_url, sensor, ae_ri):
    header = create_headers(ae_ri, '29', 'create_ts')
    timeseries_payload = {
        "m2m:ts": {
            "rn": sensor,  # Resource name for the timeseries
            "mni": 1000,  # Maximum number of instances
        }
    }

    response = requests.post(ae_url, headers=header, json=timeseries_payload, verify=False)
    if response.status_code == 201:
        print(f"TimeSeries '{sensor}' created successfully under AE {ae_url}")
    else:
        print(f"Failed to create TimeSeries '{sensor}': {response.status_code} {response.text}")

def create_subscription():
    subscription_url = MN_CSE_URL
    header = create_headers(CONFIG['MN_ORIGINATOR'], '23', 'create_sub')
    subscription_payload = {
        "m2m:sub": {
            "rn": "aeSubscription",
            "nu": [NOTIFICATION_URL],
            "nct": 1,
            "enc": {
                "net": [3]
            }
        }
    }
    
    responses = requests.get(
        subscription_url, 
        headers={"X-M2M-Origin": CONFIG['MN_ORIGINATOR'], 
                "Accept": "application/json",
                "Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}"}, 
        verify=False
    )
    
    if responses.status_code == 409:
        print("Subscription already exists. Skipping creation.")
        return

    response = requests.post(subscription_url, headers=header, json=subscription_payload, verify=False)
    if response.status_code == 201:
        print("Subscription created successfully!")
    else:
        print(f"Failed to create subscription: {response.status_code} {response.text}")

@app.route('/register_adn_ae', methods=['POST'])
@require_token
def register_adn_ae():
    data = request.json
    ae_id = data.get("ae_id")
    header = create_headers(CONFIG['MN_ORIGINATOR'], '2', 'create_ae')
    payload = {
        "m2m:ae": {
            "rn": data.get("rn", "test_sensor2"),
            "api": data.get("api", "NAppID.myapp"),
            "lbl": [],
            "rr": True,
            "srv": ["2a", "3", "4"]
        }
    }
    
    response = requests.post(IN_CSE_URL, headers=header, json=payload, verify=False)
    if response.status_code == 201:
        return jsonify({"message": "AE 등록 성공", "data": response.json()}), 201
    else:
        return jsonify({"message": "AE 등록 실패", "status": response.status_code}), response.status_code

@app.route('/notifi', methods=['POST'])
@require_token
def handle_notification():
    notification = request.get_json()
    print(f"Notification received: {json.dumps(notification, indent=4)}")

    if notification.get("m2m:sgn", {}).get("vrq", False):
        content_type = request.headers.get('Content-Type', '').lower()
        notification_data = request.json
        
        print("Received Notification:", notification_data)
        print("Headers:", dict(request.headers))

        header = create_headers('mn-ae', request.headers.get('X-M2M-RI', ''), 
                              datetime.utcnow().strftime('%Y%m%dT%H%M%S'), '2000')

        return Response(status=200, headers=header)
    
    new_ae_data = notification.get("m2m:sgn", {}).get("nev", {}).get("rep", {}).get("m2m:ae", {})
    print(f"Extracted AE Data: {new_ae_data}")

    new_ae_rn = new_ae_data.get("rn")
    new_ae_ri = new_ae_data.get("ri")
    
    if not new_ae_rn:
        print("AE Resource Name (rn) is missing in the notification.")

    if new_ae_rn=="smartBulb": #생성된 ae의 이름이 smartBulb일 경우
        print(f"{new_ae_rn} created")
        cnt_name = "status"
        ae_url = f"https://{CONFIG['MN_CSE_HOST']}:{CONFIG['MN_CSE_PORT']}/{new_ae_ri}"
        create_container(ae_url, cnt_name, new_ae_ri)
    else: # 그외의 센서가 ae로 등록될 경우
        print(f"New AE created: {new_ae_rn}")
        sensor_names = ["temperature", "humid", "light"]
        for sensor in sensor_names:
            ae_url = f"https://{CONFIG['MN_CSE_HOST']}:{CONFIG['MN_CSE_PORT']}/{new_ae_ri}"
            print(f"Creating TimeSeries Resource '{sensor}' under AE URL: {ae_url}")
            create_timeseries(ae_url, sensor, new_ae_ri)

    return jsonify({"status": "success"}), 200

@app.route('/sync_to_in_cse', methods=['POST'])
@require_token
def sync_to_in_cse():
    data = request.json
    ae_id = data.get("ae_id")
    sensor_name = data.get("sensor_name") #sensor_name이 아닌 timeseriesResource의 orginator를 따와야함
    
    response = requests.get(
        f"{MN_CSE_URL}/{ae_id}/{sensor_name}/contentInstance", #timeseriesInstance로 바꿔야함
        headers={"Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}"},
        verify=False
    )
    
    if response.status_code == 200:
        sensor_data = response.json().get("m2m:cin", {}).get("con")
        if sensor_data:
            payload = { #timeSeriesInstance에 맞게 양식 수정해야함
                "m2m:cin": {
                    "con": sensor_data
                }
            }
            response_in_cse = requests.post(
                f"{IN_CSE_URL}/{ae_id}/{sensor_name}/contentInstance",
                headers={"Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}"},
                json=payload,
                verify=False
            )
            
            if response_in_cse.status_code == 201:
                return jsonify({"message": "IN-CSE로 데이터 동기화 성공"}), 201
            else:
                return jsonify({"message": "IN-CSE로 데이터 동기화 실패", 
                              "status": response_in_cse.status_code}), response_in_cse.status_code
        else:
            return jsonify({"message": "MN-CSE에서 데이터 없음"}), 404
    else:
        return jsonify({"message": "MN-CSE에서 데이터 가져오기 실패", 
                       "status": response.status_code}), response.status_code

@app.route('/health_check', methods=['GET'])
@require_token
def health_check():
    return jsonify({
        "status": "MN-AE is running",
        "MN-CSE URL": MN_CSE_URL,
        "IN-CSE URL": IN_CSE_URL,
        "configuration": {k: v for k, v in CONFIG.items() if 'TOKEN' not in k}
    }), 200

if __name__ == '__main__':
    threading.Thread(target=create_subscription).start()
    app.run(host='0.0.0.0', debug=True, port=int(CONFIG['LOCAL_PORT']))