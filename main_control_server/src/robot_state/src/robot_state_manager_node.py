#!/usr/bin/env python3
import sys
import os
import re
import yaml
import threading
import queue
import time
import mysql.connector as con
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from modules.connect import Connect
from robot_task_client import RobotTaskClient
# 서비스 서버
from robot_state.srv import UpdateDB
# Task Manager로부터 오는 메세지 타입
from task_manager.msg import SendAllocationResults
# Robot Task Client으로부터 오는 메세지 타입
from robot_state.msg import AllTaskDone
# RackList 메시지 타입
from robot_state.msg import RackList
from std_msgs.msg import String

current_dir = os.path.dirname(os.path.abspath(__file__))
db_user_info_path = os.path.join(current_dir, "../../../../params/db_user_info.yaml")
yaml_file_path = os.path.abspath(db_user_info_path)

# YAML 파일을 읽어 파라미터를 가져옴
def load_db_params(file_path):
    with open(file_path, 'r') as file:
        params = yaml.safe_load(file)
    return params['local_db']['id'], params['local_db']['pw']

def get_mysql_connection():
    try:
        db_id, db_pw = load_db_params(yaml_file_path)
        db_instance = Connect(db_id, db_pw)
        return db_instance
    except con.Error as err:
        print(f"Error: {err}")
        return None

class UpdateRobotState():
    def __init__(self, db_instance):
        self.cursor = db_instance.cursor
        self.conn = db_instance.conn
        if not self.conn or not self.cursor:
            print("Failed to connect to the database")
            return

    # 데이터베이스에서 테이블 정보를 가져오는 함수 정의
    def fetchDataQuery(self, query):
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def loadDataFromDB(self, query):
        robot_data = self.fetchDataQuery(query)
        return robot_data

    def updateData(self, query):
        self.cursor.execute(query)
        self.conn.commit()

# 전역 변수
Robot_Name = "Debugging"
Rack_List = ["Debugging", "Debugging", "Debugging"]
Task_Assignment = "Debugging"
Task_Code = "Debugging"

# 전역 딕셔너리로 로봇별 플래그 추가 #new
robot_flags = {"Robo1": False, "Robo2": False} #new
task_sent_flags = {"Robo1": False, "Robo2": False}  # 태스크를 한번만 실행하기 위한 플래그

class MFCRobotManager(Node):
    def __init__(self):
        super().__init__('mfc_robot_manager')
        self.db_instance = get_mysql_connection()
        self.update_robot_state = UpdateRobotState(self.db_instance)
        self.update_robot_state_pub = self.create_publisher(String, 'update_robot_state', 10)

        # 'UpdateDb' 메세지 타입 서비스 서버
        self.server = self.create_service(UpdateDB, 'update_db', self.update_db_callback)
        # 'SendAllocationResults' 메세지 타입 subscriber
        self.allocation_results_sub = self.create_subscription(
            SendAllocationResults,
            'send_allocation_results',
            self.task_assignment_callback,
            10)
        self.all_task_done_sub = self.create_subscription(
            AllTaskDone,
            'send_all_task_done_results',
            self.all_task_done_callback,
            10)

    def all_task_done_callback(self, msg):
        global robot_flags #new
        global task_sent_flags #new
        global Robot_Name
        global Rack_List
        global Task_Assignment
        global Task_Code #new

        robot_name = msg.robot_name #new

        if msg.result_msg == "All done":
            rack_list_str = str(Rack_List).replace('[', '').replace(']', '').replace("'", "")
            query = f"""
                UPDATE Robot_manager
                SET Status = '대기중'
                WHERE Robot_Name = '{Robot_Name}'
                      AND Rack_List = '{rack_list_str}'
                      AND Status = '작업중'
                      AND Task_Assignment = '{Task_Assignment}';
            """
            self.update_robot_state.updateData(query)
            robot_flags[robot_name] = False  # 작업 완료 후 플래그 초기화 #new
            task_sent_flags[robot_name] = False  # 태스크 전송 플래그 초기화

            # 작업 완료 후 task_allocation 테이블 업데이트 #new
            query = f"""
                UPDATE task_allocation
                SET status = 'completed'
                WHERE task_code = '{Task_Code}';  # task_code 추가 #new
            """
            self.update_robot_state.updateData(query)
        else:
            self.get_logger().info("작업중...")

    def update_db_callback(self, request, response):
        robot_name = request.robot_name
        query = f"SELECT Robot_Name, Status, Estimated_Completion_Time, Battery_Status FROM Robot_manager WHERE Robot_Name = '{robot_name}' ORDER BY Time DESC LIMIT 1;"
        robot_data = self.update_robot_state.loadDataFromDB(query)
        self.get_logger().info(f'{robot_data}')
        response.robot_name = robot_data[0][0]
        response.status = robot_data[0][1]
        response.estimated_completion_time = robot_data[0][2]
        response.battery_status = robot_data[0][3]
        return response

    def task_assignment_callback(self, msg):
        global robot_flags
        global task_sent_flags
        global Robot_Name
        global Task_Code
        global Rack_List
        global Task_Assignment

        robot_name = msg.robot_name

        if not robot_flags.get(robot_name, False):  # 로봇이 작업 중이 아닐 때만 작업 할당
            self.get_logger().info(f'Received task assignment for robot: {msg.robot_name}')  # 1번 출력
            self.get_logger().info(f'Task Code: {msg.task_code}')
            self.get_logger().info(f'Rack List: {msg.rack_list}')
            self.get_logger().info(f'Task Assignment: {msg.task_assignment}')

            # 로봇 이름 및 목표 위치 전달
            robot_flags[robot_name] = True  # 작업 할당 시 플래그 설정
            Robot_Name = msg.robot_name
            Task_Code = msg.task_code
            Rack_List = msg.rack_list
            Task_Assignment = msg.task_assignment
            estimated_completion_time = len(Rack_List)
            rack_list_str = str(Rack_List).replace('[', '').replace(']', '').replace("'", "")  # Format Rack_List correctly

            print(estimated_completion_time)
            print(rack_list_str)
            print('################################################################')

            # Robot_manager 테이블 업데이트
            num = 1 if Robot_Name == 'Robo1' else 2
            query = f"""
                UPDATE Robot_manager
                SET
                    Num = {num},
                    Location_X = 0.0,
                    Location_Y = 0.0,
                    Rack_List = '{rack_list_str}',
                    Status = '작업중',
                    Estimated_Completion_Time = {float(estimated_completion_time)},
                    Battery_Status = '100%',
                    Task_Assignment = '{Task_Assignment}',
                    Error_Codes = 'None',
                    Time = NOW()
                WHERE
                    Robot_Name = '{Robot_Name}';
            """
            self.update_robot_state.updateData(query)
            self.get_logger().info(f"Succeeding to update in Robot_manager")

            # task_allocation 테이블 업데이트
            query = f"""
                UPDATE task_allocation
                SET
                    status = 'assigned',
                    robot = '{Robot_Name}'
                WHERE
                    task_code = '{Task_Code}';
            """
            self.update_robot_state.updateData(query)
            self.get_logger().info(f"Succeeding to update in task_allocation")

            # Task_Manager에게 업데이트 신호 전송
            msg = String()
            msg.data = 'robot_state_updated'
            self.update_robot_state_pub.publish(msg)
            self.get_logger().info(f"Send robot_state_updated to Task Manager")
        else:
            self.get_logger().info(f"Robot {robot_name} is currently busy with another task.")
            # Robot이 작업 중인 경우 task_allocation 테이블 업데이트
            query = f"""
                UPDATE task_allocation
                SET
                    status = 'pending',
                    robot = '{robot_name}'
                WHERE
                    task_code = '{msg.task_code}';
            """
            self.update_robot_state.updateData(query)
            self.get_logger().info(f"Updated task_allocation table with pending status for task_code: {msg.task_code}")

def main(args=None):
    global Robot_Name
    global Rack_List
    global Task_Code  # new
    global Task_Assignment
    rclpy.init(args=args)
    executor = MultiThreadedExecutor()
    node1 = MFCRobotManager()
    node2 = RobotTaskClient()
    executor.add_node(node1)
    executor.add_node(node2)
    print("Update 전 초기값")                                                               # 0번 출력
    print(Robot_Name, Rack_List, Task_Assignment)
    print('################################################################')
    try:
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.1)
            for robot_name in robot_flags:  # new
                if robot_flags[robot_name] and not task_sent_flags[robot_name]:  # 로봇이 작업 중이지만 태스크가 전송되지 않은 경우
                    print("Update 후")                                                         # 3번 출력
                    print(Robot_Name, Task_Code, Rack_List, Task_Assignment)                   # 5번 출력
                    node2.receive_goal_list(Robot_Name, Rack_List, Task_Assignment)            # 6번 출력
                    print('################################################################')
                    task_sent_flags[robot_name] = True  # 태스크 전송 플래그 설정
    finally:
        node1.update_robot_state.conn.close()  # 프로그램 종료 시 연결 닫기
        executor.shutdown()
        node1.destroy_node()
        node2.destroy_node()
        rclpy.shutdown()
if __name__ == '__main__':
    main()
