from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
from datetime import datetime
import threading
import time

app = Flask(__name__)

# MN-CSE 및 IN-CSE의 엔드포인트
MN_CSE_URL = "http://localhost:8080/id-in"
IN_CSE_URL = "http://localhost:8080/id-in" #in cse로 바꿔줘야함
AE_ID = 'ID-IN'

# 각 request에 맞는 onem2m 표준 header 생성
def create_headers(originator: str, resource_type: str = None, request_id: str = None, time: str = None, rsc: str = None) -> dict: 
    headers = {
        "Accept": "application/json;",
        "X-M2M-Origin": originator,
        "X-M2M-RVI": "2a"
    }

    if rsc:
        headers["X-M2M-RSC"] = rsc

    if resource_type:  # 리소스 타입
        headers["Content-Type"] = 'application/json;ty=' + resource_type

    if request_id:  # 요청 식별자
        headers["X-M2M-RI"] = request_id

    if time:
        headers["'X-M2M-OT'"] = time

    return headers

# 생성된 mn-cse의 ae에 Container 생성 함수
def create_container(ae_url, sensor, ae_ri):
    header = create_headers(ae_ri,'3','creat_cnt')
    container_payload = {
        "m2m:cnt": {
            "rn": sensor
        }
    }

    response = requests.post(ae_url, headers=header, json=container_payload)
    if response.status_code == 201:
        print(f"Container '{sensor}' created successfully under AE {ae_url}")
    else:
        print(f"Failed to create container '{sensor}': {response.status_code} {response.text}")

# mn-cse에 ae생성에 대한 Subscription 생성 함수, 서버 시작시 동작
def create_subscription():
    subscription_url = f"{MN_CSE_URL}"
    header = create_headers('CAdmin', '23', 'create_sub') # mn쪽 originator를 알아내고 가져와야함.
    subscription_payload = {
        "m2m:sub": {
            "rn": "aeSubscription",
            "nu": ["http://192.168.0.2:5000/notifi"],
            "nct": 1,
            "enc": {
                "net": [3]  # Event type: Resource Creation
            }
        }
    }
    responses = requests.get(subscription_url, headers={"X-M2M-Origin": "CAdmin", "Accept": "application/json"})
    if responses.status_code == 409: #잘 안먹힘 나중에 다시 봐야할듯
        print("Subscription already exists. Skipping creation.")
        return  # 이미 존재하므로 생성하지 않음
    response = requests.post(subscription_url, headers=header, json=subscription_payload)
    if response.status_code == 201:
        print("Subscription created successfully!")
    else:
        print(f"Failed to create subscription: {response.status_code} {response.text}")

# IN-cse에 ADN-AE 등록, 서버시작시 동작
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

# Notification 처리 엔드포인트
@app.route('/notifi', methods=['POST'])
def handle_notification():
    notification = request.get_json()
    print(notification)  # Debug: 수신된 알림 원본 출력
    print(f"Notification received: {json.dumps(notification, indent=4)}")

    # Verification Request 확인
    if notification.get("m2m:sgn", {}).get("vrq", False):
        content_type = request.headers.get('Content-Type', '').lower()
        if content_type == 'application/json':
            notification_data = request.json  # JSON 형식의 데이터
        elif content_type == 'application/vnd.onem2m-res+json':
            notification_data = request.json  # oneM2M JSON 형식

        # 요청 데이터 디버깅용 출력
        print("Received Notification:", notification_data)
        print("Headers:", dict(request.headers))

        # 응답 생성
        header = create_headers('mn-ae', request.headers.get('X-M2M-RI', ''), datetime.utcnow().strftime('%Y%m%dT%H%M%S'), '2000')

        # 상태 코드 200 OK 반환
        return Response(status=200, headers=header)
    
    # 실제 알림 처리
    # AE URL 추출
    new_ae_data = notification.get("m2m:sgn", {}).get("nev", {}).get("rep", {}).get("m2m:ae", {})
    print(f"Extracted AE Data: {new_ae_data}")  # 디버깅용 출력

    new_ae_rn = new_ae_data.get("rn")  # 'rn' 필드 값 추출
    new_ae_ri = new_ae_data.get("ri")
    if not new_ae_rn:
        print("AE Resource Name (rn) is missing in the notification.")

    if new_ae_rn:
        print(f"New AE created: {new_ae_rn}")

        # 센서별 Container 생성
        sensor_names = ["temperature", "humid", "light"]
        for sensor in sensor_names:
            ae_url = f"http://localhost:8080/{new_ae_ri}"
            print(f"Creating container '{sensor}' under AE URL: {ae_url}")  # Debug: 컨테이너 생성 로그
            create_container(ae_url, sensor, new_ae_ri)

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
    threading.Thread(target=create_subscription).start()
    app.run(host='0.0.0.0', debug=True, port=5000)