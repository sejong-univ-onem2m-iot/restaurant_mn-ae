from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
from datetime import datetime
import threading
import time
from functools import wraps
import os
import threading
import warnings
warnings.filterwarnings('ignore')

CONFIG = {
    'IN_CSE_HOST': '127.0.0.1',
    'IN_CSE_PORT': '4000',
    'LOCAL_HOST': '192.168.0.2',#'192.168.0.2',172.16.25.175
    'LOCAL_PORT': '5761',
    'AUTH_TOKEN': os.getenv('AUTH_TOKEN'),
    'MN_ORIGINATOR': "CAdmin",
    'MN_CSE_HOST': '127.0.0.1',
    'MN_CSE_PORT': '4000'
}
# URLs
MN_CSE_URL = f"https://{CONFIG['MN_CSE_HOST']}:{CONFIG['MN_CSE_PORT']}/id-in"
IN_CSE_URL = f"https://{CONFIG['IN_CSE_HOST']}:{CONFIG['IN_CSE_PORT']}/id-in"
NOTIFICATION_URL = f"http://{CONFIG['LOCAL_HOST']}:{CONFIG['LOCAL_PORT']}/notifi"

app = Flask(__name__)
CORS(app)
ts_id = [] #ts_id param

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
        "Accept": "application/json",
        "X-M2M-Origin": originator,
        "X-M2M-RVI": "3",
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

def register_mn_ae(): #mn-ae에대한 ae를 in-cse에 생성 요청하는 코드 // NO DEBUGGING
    mn_ae_ori = "myRestaurant1" #환경변수로 따로 설정필요->레스토랑 이름으로 입력시키면 아주 간편
    header = create_headers(f"C{mn_ae_ori}", '2', 'create_ae')

    payload = {
        "m2m:ae": {
            "rn": mn_ae_ori,
            "api": f"N{mn_ae_ori}.myapp",
            "lbl": ["test"],
            "rr": True,
            "srv": ["2a", "3", "4"]
        }
    }
    
    response = requests.post(IN_CSE_URL, headers=header, json=payload, verify=False)
    if response.status_code == 201:
        print("message: AE 등록 성공\n data:", response.json())

def create_container(ae_url, sensor, ae_ri): #
    header = create_headers(ae_ri, '3', 'creat_cnt')
    container_payload = {
        "m2m:cnt": {
            "rn": 'command'
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
            "mni": 4320,  # Maximum number of instances for a month
        }
    }

    response = requests.post(ae_url, headers=header, json=timeseries_payload, verify=False)
    print("response content", response.json())
    
    if response.status_code == 201:
        response_data = response.json()
        ri = response_data.get("m2m:ts", {}).get("ri")  # Extract the 'ri' value
        print(f"TimeSeries '{sensor}' created successfully under AE {ae_url}")
        print(f"Extracted Resource ID (ri): {ri}")
        return ri  # Return the extracted 'ri'
    else:
        print(f"Failed to create TimeSeries '{sensor}': {response.status_code} {response.text}")
        return None  # Return None if the creation failed

def create_subscription():
    time.sleep(2)
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

@app.route('/notifi', methods=['POST'])
#@require_token
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
        sensor_names = ["temperature", "humid", "noise"]
        for sensor in sensor_names:
            ae_url = f"https://{CONFIG['MN_CSE_HOST']}:{CONFIG['MN_CSE_PORT']}/{new_ae_ri}"
            print(f"Creating TimeSeries Resource '{sensor}' under AE URL: {ae_url}")
            ts_id.append(create_timeseries(ae_url, sensor, new_ae_ri))

    return jsonify({"status": "success"}), 200

def create_group(cnt_ri, ts_id):
    header = create_headers(f"C{cnt_ri}", '9', 'create_grp')
    group_payload = {
        "m2m:grp": {
            "rn": "sensor_grp",  # Resource name for the timeseries
            "mnm": 10, #maximum member number a
            "mid": ts_id
        }
    }

    response = requests.post(f"https://{CONFIG['MN_CSE_HOST']}:{CONFIG['MN_CSE_PORT']}/C{cnt_ri}", headers=header, json=group_payload, verify=False)
    if response.status_code == 201:
        print(f"Group sensor_grp created successfully under AE {cnt_ri}")
    else:
        print(f"Failed to create TimeSeries sensor_grp: {response.status_code} {response.text}")

@app.route('/sync_to_in_cse', methods=['POST'])
#@require_token
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
# 수정해야할 코드 12.03
"""
CONFIG = {
    'MN_CSE_URL': "https://192.168.0.8:3000/cse-in/Sensor/grp_uaCwwSWq7k/fopt/la",  # MN-CSE URL
    'IN_CSE_URL': "https://192.168.0.9:3000/cse-in/Sensor",  # IN-CSE URL
    'AUTH_TOKEN': "your_auth_token_here",  # Authorization Token
    'HEADERS': {
        "Accept": "application/json",
        "X-M2M-RI": "12345",
        "X-M2M-Origin": "Sensors",
        "X-M2M-RVI": "3"
    }
}
"""
def fetch_from_mn_cse():
    #Fetch the latest data from MN-CSE.
    header = create_headers("myRestaurant1", None, "fetch_data", None, "3") #originator를 영민 코드에선 Sensors
    try:
        response = requests.get(
            f"{MN_CSE_URL}/Sensor/{GRP_RN}/fopt/la", headers=header, verify=False
        )
        if response.status_code == 200:
            print("Fetched data from MN-CSE successfully!")
            print("fetched data: ", response.json())
            return response.json()
        else:
            print(f"Failed to fetch from MN-CSE: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching from MN-CSE: {e}")
        return None

def send_to_in_cse(data):
    """Send the processed data to IN-CSE."""
    try:
        headers = CONFIG['HEADERS']
        headers["X-M2M-Origin"] = "CAdmin"  # Update originator for IN-CSE
        
        response = requests.post(
            CONFIG['IN_CSE_URL'], headers=headers, json=data, verify=False
        )
        if response.status_code == 201:
            print("Data sent to IN-CSE successfully!")
        else:
            print(f"Failed to send to IN-CSE: {response.status_code} {response.text}")
    except Exception as e:
        print(f"Error sending to IN-CSE: {e}")


@app.route('/sync_data', methods=['GET'])
def sync_data():
    """Fetch data from MN-CSE, process it, and send it to IN-CSE."""
    # Fetch data from MN-CSE
    mn_cse_data = fetch_from_mn_cse()
    if not mn_cse_data:
        return jsonify({"message": "Failed to fetch data from MN-CSE"}), 500

    # Process the data (assuming we want to restructure it)
    processed_data = process_mn_cse_data(mn_cse_data)

    # Send the processed data to IN-CSE
    send_to_in_cse(processed_data)

    return jsonify({"message": "Data synced successfully"}), 200


def process_mn_cse_data(mn_cse_data):
    """Process the data fetched from MN-CSE."""
    try:
        # Extract the response payload
        responses = mn_cse_data.get("m2m:agr", {}).get("m2m:rsp", [])
        processed = []

        for resp in responses:
            # Extract the timeseries instance content
            content_instance = resp.get("pc", {}).get("m2m:tsi", {}) #어떻게 처리해서 보낼진 영민이랑 상의
            if content_instance:
                processed.append({
                    "con": content_instance.get("con"),  # Data content
                    "ts": content_instance.get("ct"),   # Creation timestamp
                    "rn": content_instance.get("rn"),   # Resource name
                })
        
        # Format the data as required for IN-CSE
        return {
            "m2m:tsi_batch": processed  # m2m:tsi_batch이유는 감싸서 전달하면 반복적으로 tsi 인스턴스를 생성한다는것 같음 실험해봐야함.
        }
    except Exception as e:
        print(f"Error processing MN-CSE data: {e}")
        return {}
# 수정해야할 코드 12.03
@app.route('/health_check', methods=['GET'])
#@require_token
def health_check():
    return jsonify({
        "status": "MN-AE is running",
        "MN-CSE URL": MN_CSE_URL,
        "IN-CSE URL": IN_CSE_URL,
        "configuration": {k: v for k, v in CONFIG.items() if 'TOKEN' not in k}
    }), 200

init_task_done = threading.Event()

def start_init_tasks():
    if not init_task_done.is_set():
        time.sleep(2)
        create_subscription()
        register_mn_ae()
        time.sleep(2)
        print("ts_id list: ", ts_id)
        create_group("myRestaurant1", ts_id)
        init_task_done.set()

if __name__ == '__main__':
    threading.Thread(target=start_init_tasks).start()
    app.run(host='0.0.0.0', debug=True, port=int(CONFIG['LOCAL_PORT']))