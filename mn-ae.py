from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# MN-CSE 및 IN-CSE의 엔드포인트
MN_CSE_URL = "http://localhost:8080/id-in"
IN_CSE_URL = "http://localhost:8080/id-in" #in cse로 바꿔줘야함
AE_ID = 'ID-IN'

def create_headers(originator: str, resource_type: str = None, request_id: str = None) -> dict:
    """
    공통 헤더 생성 함수.

    Args:
        originator (str): 요청의 Originator.
        resource_type (str): 리소스 유형 (예: `application/json;ty=2`).
        request_id (str): 요청 식별자 (필요시).

    Returns:
        dict: 생성된 헤더.
    """
    headers = {
        "Accept": "application/json;",
        "X-M2M-Origin": originator,
        "X-M2M-RVI": "2a"
    }

    if resource_type:  # 리소스 타입이 필요한 경우 추가
        headers["Content-Type"] = 'application/json;ty='+ty,

    if request_id:  # 요청 식별자가 필요한 경우 추가
        headers["X-M2M-RI"] = request_id

    return headers

HEADER = {
  'Accept': 'application/json;', 
  'X-M2M-RI': '', #create_ae
  'X-M2M-origin': '', #CAdmin2
  'Content-Type': '', #application/json;ty=2
  'X-M2M-RVI': '2a'
} 

# IN-cse에 ADN-AE 등록
@app.route('/register_adn_ae', methods=['POST'])
def register_adn_ae():
    data = request.json
    ae_id = data.get("ae_id")
    header = create_headers('CAdmin', '2','create_ae')
    payload = {
        "m2m:ae":{
            "rn": "test_sensor2", #이거 변수로
            "api": "NAppID.myapp",#이거 변수로
            "lbl": [],
            "rr": True,
            "srv": ["2a", "3", "4"]
        }
    }
    response = requests.post(f"{IN_CSE_URL}", headers = header, json=payload)
    if response.status_code == 201:
        return jsonify({"message": "AE 등록 성공", "data": response.json()}), 201
    else:
        return jsonify({"message": "AE 등록 실패", "status": response.status_code}), response.status_code

# mn-cse에 ae생성에 대한 Subscription 생성 함수
def create_subscription():
    subscription_url = f"{MN_CSE_BASE_URL}/cse-in"
    header = create_headers('CAdmin', '23','create_sub')
    subscription_payload = {
        "m2m:sub": {
            "rn": "aeSubscription",
            "nu": [f"http://localhost:5000/notification"],
            "nct": 1,
            "enc": {
                "net": [3]  # Event type: Resource Creation
            }
        }
    }

    response = requests.post(subscription_url, headers=header, json=subscription_payload)
    if response.status_code == 201:
        print("Subscription created successfully!")
    else:
        print(f"Failed to create subscription: {response.status_code} {response.text}")

# 생성된 mn-cse의 ae에 Container 생성 함수
def create_container(ae_url, sensor):
    
    container_payload = {
        "m2m:cnt": {
            "rn": sensor
        }
    }

    response = requests.post(ae_url, headers=headers, json=container_payload)
    if response.status_code == 201:
        print(f"Container '{container_name}' created successfully under AE {ae_url}")
    else:
        print(f"Failed to create container '{container_name}': {response.status_code} {response.text}")

# Notification 처리 엔드포인트
@app.route('/notification', methods=['POST'])
def handle_notification():
    notification = request.get_json()
    print(f"Notification received: {json.dumps(notification, indent=4)}")

    # AE URL 추출
    new_ae_url = notification.get("m2m:sgn", {}).get("sur")
    if new_ae_url:
        print(f"New AE created: {new_ae_url}")

        # 센서별 Container 생성
        sensor_names = ["temperatureSensor", "humiditySensor", "lightSensor"]
        for sensor in sensor_names:
            create_container(new_ae_url, sensor)

    return jsonify({"status": "success"}), 200

# MN-CSE로부터 데이터를 가져와 IN-CSE로 전달
@app.route('/sync_to_in_cse', methods=['POST'])
def sync_to_in_cse():
    data = request.json
    ae_id = data.get("ae_id")
    sensor_name = data.get("sensor_name")
    # MN-CSE에서 데이터 가져오기
    response = requests.get(f"{MN_CSE_URL}/{ae_id}/{sensor_name}/contentInstance")
    if response.status_code == 200:
        sensor_data = response.json().get("m2m:cin", {}).get("con")
        if sensor_data:
            # IN-CSE로 데이터 전송
            payload = {
                "m2m:cin": {
                    "con": sensor_data
                }
            }
            response_in_cse = requests.post(f"{IN_CSE_URL}/{ae_id}/{sensor_name}/contentInstance", json=payload)
            if response_in_cse.status_code == 201:
                return jsonify({"message": "IN-CSE로 데이터 동기화 성공"}), 201
            else:
                return jsonify({"message": "IN-CSE로 데이터 동기화 실패", "status": response_in_cse.status_code}), response_in_cse.status_code
        else:
            return jsonify({"message": "MN-CSE에서 데이터 없음"}), 404
    else:
        return jsonify({"message": "MN-CSE에서 데이터 가져오기 실패", "status": response.status_code}), response.status_code

# 상태 확인 및 모니터링 (관리)
@app.route('/health_check', methods=['GET'])
def health_check():
    return jsonify({"status": "MN-AE is running", "MN-CSE URL": MN_CSE_URL, "IN-CSE URL": IN_CSE_URL}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
