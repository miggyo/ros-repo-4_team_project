#!/usr/bin/env python3
import yaml
import rclpy
from rclpy.node import Node
import os
from task_manager.msg import DbUpdate, GuiUpdate
from task_manager.msg import StartInspection, InspectionComplete, SendAllocationResults, SendLightOffResults
from task_manager.srv import GenerateOrder, AllocatorTask
from modules.order_grouping import group_items
from modules.order_list import OrderList  
from robot_state.srv import UpdateDB
from std_msgs.msg import String  # String 메시지 타입을 사용


# Robot Task Client 로부터 오는 메세지 타입
from robot_state.msg import TaskProgressUpdate
import mysql.connector as con

class OrderListService(Node):
    def __init__(self):
        super().__init__('order_list_service')
        self.order_list_node = OrderList()
        self.grouped_items = []

        self.inspection_started = False  # 플래그 변수 초기화
        self.inspection_started = False  # 플래그 변수 초기화
        self.initial_task_allocation = False
        self.robot_state_dbupdate = False


        self.inspection_index = 0  # 검수 진행 중인 아이템 인덱스
        self.total_items_to_inspect = 0
        self.inspected_items_count = 0

        self.current_task_code = None # 현재 그룹의 task_code를 저장할 변수 추가
        self.product_code_list = []  # 현재 그룹의 product_code 리스트를 저장할  변수 추가
        self.robot_info_list = []  # 로봇 정보를 저장할 리스트  # 로봇 정보를 저장할 변수 삐삐 뽀뽀~
        self.robot_names = ["Robo1", "Robo2"]  # 모든 로봇 이름 리스트

        
        
#------------------------------------publisher--------------------------------------

        # 'StartInspection' 메세지 타입의 publisher
        self.publisher_start_inspection = self.create_publisher(StartInspection, 'mfc_start_inspection', 10)

        # 'SendLightOffResults' 메세지 타입의 publisher
        self.publisher_light_off_results = self.create_publisher(SendLightOffResults, 'send_light_off_results', 10)     

        # 'GuiUpdate' 메세지 타입의 publisher
        self.publisher_update_gui = self.create_publisher(GuiUpdate, 'gui_update', 10) 

        # 'SendAllocationResults' 메세지 타입의 publisher
        self.publisher_allocation_results = self.create_publisher(SendAllocationResults, 'send_allocation_results', 10)


#------------------------------------subscriber--------------------------------------

        # 'DbUpdate' 메세지 타입의 subscriber
        self.subscription = self.create_subscription(
            DbUpdate,
            'db_update_status',
            self.db_update_callback,
            10)
        self.subscription 

        # 'InspectionComplete' 메세지 타입의 subscriber
        self.subscription_inspection_complete = self.create_subscription(
            InspectionComplete,
            'inspection_complete',
            self.inspection_complete_callback,
            10)
        self.subscription_inspection_complete

        # 'TaskProgressUpdate' 메세지 타입의 subscriber
        self.subscription_task_progress_update = self.create_subscription(                                   
            TaskProgressUpdate,
            'send_task_complete_results',
            self.task_progress_callback,
            10
            )
        self.subscription_task_progress_update  

        # 'String' 메세지 타입의 subscriber
        self.subscription_robot_state_updated = self.create_subscription(
            String,
            'update_robot_state',
            self.robot_state_updated_callback,
            10
        )
        self.subscription_robot_state_updated

#------------------------------------servece server--------------------------------------

        # 'GenerateOrder' 메세지 타입의 서비스 서버
        self.srv = self.create_service(GenerateOrder, 'generate_order', self.generate_order_callback)    

#------------------------------------servece client--------------------------------------

        # 'AllocatorTask' 메세지 타입의 서비스 클라이언트 
        self.task_allocator_client = self.create_client(AllocatorTask, 'allocate_task')
        while not self.task_allocator_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('allocate_task service not available, waiting again...')
        self.get_logger().info('allocate_task service available.')

        

        # 'UpdateDB' 서비스 타입의 클라이언트
        self.client_update_dB = self.create_client(UpdateDB, 'update_db')
        while not self.client_update_dB.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('UpdateDB Service not available, waiting again...')
        self.get_logger().info('UpdateDB Service available, ready to send request.')

        for robot_name in self.robot_names:
            self.updateDB_client(robot_name)

#-----------------------------------------------------------------------------------------

    def updateDB_client(self,robot_name):
        if not self.client_update_dB:
            self.get_logger().error('Client not initialized')
            return
        request = UpdateDB.Request()
        # 'UpdateDB' 서비스 Request 메세지 타입: Robot_Name
        request.robot_name = robot_name                     # 디버깅용
        future = self.client_update_dB.call_async(request)       
        future.add_done_callback(self.callback_response)  # 응답 콜백 설정

    def task_progress_callback(self, msg):                                                                     
        self.get_logger().info(f'Received task progress from robot_state_manager: {msg.robot_name}')                       
        self.get_logger().info(f'Current Rack: {msg.current_rack}')                                                   
        self.get_logger().info(f'Task Complete: {msg.task_complete}')
        self.get_logger().info(f'****************************************************')
        
        self.send_light_off_results(msg.current_rack, msg.task_complete)

        # 재고 수량 업데이트 로직 추가
        self.update_inventory(msg.current_rack)

    def send_light_off_results(self, current_rack, task_complete):                                        
        light_off_msg =  SendLightOffResults()
        light_off_msg.current_rack = current_rack
        light_off_msg.task_complete = task_complete
        
        self.publisher_light_off_results.publish(light_off_msg)

    def update_inventory(self, rack):
        db_connection = Connect("root", "asdf")
        cursor = db_connection.cursor
        try:
            # Rack 값에서 앞의 'R_'를 제거하고 두 글자만 남김
            simplified_rack = rack[2:]

            # Inbound_Manager 테이블에서 해당 랙의 수량 가져오기
            select_query = f"SELECT Receiving_Quantity FROM Inbound_Manager WHERE Rack LIKE '%{simplified_rack}'"
            cursor.execute(select_query)
            result = cursor.fetchone()
            
            if result:
                quantity = result[0]
                self.get_logger().info(f"Current quantity for rack {rack}: {quantity}")
                
                # Inventory 테이블의 Quantity 업데이트
                update_query = f"UPDATE Inventory SET Receiving_Quantity = Receiving_Quantity + {quantity} WHERE Rack = '{rack}'"
                cursor.execute(update_query)
                db_connection.conn.commit()
                self.get_logger().info(f"Updated inventory for rack {rack}. New receiving quantity: {quantity}")
            else:
                self.get_logger().warning(f"No quantity found for rack {rack} in Inbound_Manager")
                    
        except con.Error as err:
            self.get_logger().error(f"Error updating inventory: {err}")
        finally:
            db_connection.disConnection()
    def callback_response(self, future):
        try:
            response = future.result()
            self.get_logger().info(f'Received response: \n{response.robot_name}, {response.status}, {response.battery_status},{response.estimated_completion_time}  ')
            self.robot_info_list.append(response)

            if len(self.robot_info_list) == len(self.robot_names):
                self.saved_all_robot_info = True
                self.get_logger().info("All robot information saved.")
                
        except Exception as e:
            self.get_logger().error(f'Failed to receive response: {e}')
            self.robot_info = None

    def generate_order_callback(self, request, response):                                                        
        random_items = self.order_list_node.get_random_order_list()  # 랜덤 주문 리스트 생성

        # 중복 제거를 위해 아이템 ID 리스트를 집합으로 변환 후 다시 리스트로 변환
        order_list = list(set(item.item_id for item in random_items))
        
        # 그룹핑된 아이템 목록 생성
        self.inspection_index = 0  # 초기화 추가
        self.inspection_started = False  # 초기화 추가
        self.current_task_code = None  # 초기화 추가
        self.product_code_list = []  # 초기화 추가
        self.grouped_items = []  # 초기화 추가

        grouped_items = group_items(order_list)
        
        print(f"{grouped_items}")
        task_code = 1

        for group in grouped_items:
            for product_code in group:
                self.grouped_items.append((task_code, product_code))
            task_code += 1

        # 그룹핑된 아이템 목록 출력 (디버깅용)
        for i, (task,item) in enumerate(self.grouped_items):
            self.get_logger().info(f"Task_{task}: {item}")
        product_to_location = {
            "P01": "R_A1", "P02": "R_A2", "P03": "R_A3",
            "P04": "R_B1", "P05": "R_B2", "P06": "R_B3",
            "P07": "R_C1", "P08": "R_C2", "P09": "R_C3",
            "P10": "R_D1", "P11": "R_D2", "P12": "R_D3",
            "P13": "R_E1", "P14": "R_E2", "P15": "R_E3",
            "P16": "R_F1", "P17": "R_F2", "P18": "R_F3",
        }

        warehouses = []
        racks = []
        cells = []

        for item in random_items:
            location = product_to_location.get(item.item_id, "R_A1")  # 기본값으로 "R_A1" 설정
            warehouse, rack, cell = location.split("_")[1][0], location.split("_")[1], location.split("_")[1][1]
            warehouses.append(f"{warehouse}구역")
            racks.append(rack)
            cells.append(cell)

        response.item_ids = [str(item.item_id) for item in random_items]
        response.names = [item.name for item in random_items]
        response.quantities = [item.quantity for item in random_items]
        response.warehouses = warehouses
        response.racks = racks
        response.cells = cells
        response.statuses = ["입하완료" for _ in random_items]  # 임의로 Status 설정
        # self.get_logger().info(f'Received request: {request}')
        # self.get_logger().info(f'Sending response: {response}')

        return response

    def db_update_callback(self, msg):
        self.get_logger().info(f'Received DB update status: {msg.status}')
        if msg.status == "DB Update Completed" and not self.inspection_started:
            self.inspection_started = True
            self.get_items_to_inspect()
            self.process_next_item()
            
    def send_signal_start_inspection_to_mfc(self, product):
        self.inspection_started = False  # 신호 전송 후 플래그 설정
        msg = StartInspection()
        msg.product_code = product["Product_Code"]
        msg.product_name = product["Product_Name"]
        msg.receiving_quant = str(product["Receiving_Quant"])
        self.publisher_start_inspection.publish(msg)
        self.get_logger().info(f'Sending inspection start signal for {product["Product_Name"]}')

    
    def get_items_to_inspect(self):
        db_connection = Connect("root", "asdf")
        cursor = db_connection.cursor
        cursor.execute("SELECT COUNT(*) FROM Inbound_Manager WHERE Status = '입하완료'")
        self.total_items_to_inspect = cursor.fetchone()[0]
        self.get_logger().info(f"Total item at index { self.total_items_to_inspect}")
        db_connection.disConnection()

    def process_next_item(self):
        if self.inspection_index < len(self.grouped_items):
            task_code, item_id = self.grouped_items[self.inspection_index]
            if self.current_task_code != task_code:
                self.current_task_code = task_code
                self.product_code_list = []
            self.product_code_list.append(item_id)
            product = self.get_item_from_db(item_id)
            if product:
                self.send_signal_start_inspection_to_mfc(product)
                self.inspection_index += 1
        else:
            self.inspection_started = False
            self.get_logger().info('No more items to inspect.')

    def get_item_from_db(self, item_id):
        db_connection = Connect("root", "asdf")
        cursor = db_connection.cursor
        cursor.execute("SELECT * FROM Inbound_Manager WHERE Product_Code = %s", (item_id,))
        row = cursor.fetchone()
        self.get_logger().info(f"Fetched row from DB for Product_Code {item_id}: {row}")
        db_connection.disConnection()
        
        if row:
            product = {
                "No": row[0],
                "Product_Code": row[1],
                "Product_Name": row[2],
                "Warehouse": row[3],
                "Rack": row[4],
                "Cell": row[5],
                "Receiving_Quant": row[6],
                "Status": row[7]
            }
            return product
        return None
    

    def inspection_complete_callback(self, msg):
        self.get_logger().info(f'Inspection complete for product: {msg.product_code}')
        self.update_status_in_db(msg.product_code, '검수완료')
        self.send_update_signal_to_gui(msg.product_code, '검수완료')

        self.inspected_items_count += 1

        # 다음 인덱스가 현재 작업 코드와 다를 경우
        if (self.inspection_index < len(self.grouped_items) and self.grouped_items[self.inspection_index][0] != self.current_task_code):
            self.add_task_to_db(self.current_task_code, self.product_code_list)
            self.request_robot_info_and_allocate_task(self.current_task_code, self.product_code_list)

        # 모든 검수가 완료되었을 경우
        if self.inspected_items_count == self.total_items_to_inspect:
            self.add_task_to_db(self.current_task_code, self.product_code_list)  # 마지막 task_code 저장
            self.request_robot_info_and_allocate_task(self.current_task_code, self.product_code_list)
            self.get_logger().info('All inspections complete. Sending task allocation requests.')
        
        self.process_next_item()

    def add_task_to_db(self, task_code, product_code_list):
        db_connection = Connect("root", "asdf")
        cursor = db_connection.cursor
        query = """
            INSERT INTO task_allocation (task_code, status, robot, product_1, product_2, product_3, complete_1, complete_2, complete_3, task_complete)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            product_1 = VALUES(product_1),
            product_2 = VALUES(product_2),
            product_3 = VALUES(product_3),
            complete_1 = VALUES(complete_1),
            complete_2 = VALUES(complete_2),
            complete_3 = VALUES(complete_3),
            task_complete = VALUES(task_complete)
        """
        cursor.execute(query, (
            f'task_{task_code}',
            'pending',
            None,
            product_code_list[0] if len(product_code_list) > 0 else None,
            product_code_list[1] if len(product_code_list) > 1 else None,
            product_code_list[2] if len(product_code_list) > 2 else None,
            False,
            False,
            False,
            False
        ))
        db_connection.conn.commit()
        self.get_logger().info(f"Task {task_code} with products {product_code_list} added to the database.")
        db_connection.disConnection()


    def robot_state_updated_callback(self, msg):
        self.get_logger().info(f'Received message on robot_state_updated topic: {msg.data}')
        self.get_logger().info(f'Received message: {msg.data}')
        if msg.data == 'robot_state_updated':
            pass

        
    def update_status_in_db(self, product_code, status):        
        db_connection = Connect("root", "asdf")
        if not db_connection.conn or not db_connection.cursor:
            self.get_logger().error("Failed to connect to the database")
            return

        try:
            cursor = db_connection.cursor
            cursor.execute("UPDATE Inbound_Manager SET Status = %s WHERE Product_Code = %s", (status, product_code))
            db_connection.conn.commit()
            self.get_logger().info(f'Status for product {product_code} updated to {status} in DB')
        except con.Error as err:
            self.get_logger().error(f"Error: {err}")
        finally:
            db_connection.disConnection()


    def send_update_signal_to_gui(self, product_code, status):
        msg = GuiUpdate()
        msg.product_code = product_code
        msg.status = status
        msg.message = f"Product {product_code} status updated to {status}"
        self.publisher_update_gui.publish(msg)
        self.get_logger().info(f'Sent GUI update signal for product {product_code} with status {status}')


    def request_robot_info_and_allocate_task(self,task_code,product_code_list):
        robot_names = ["Robo1", "Robo2"]  # 모든 로봇 이름 리스트

        allocation_target_task_code=task_code
        allocation_target_product_code_list=product_code_list

        for robot_name in robot_names:
            self.updateDB_client(robot_name)

        if(self.saved_all_robot_info==True):# 모든 로봇 정보를 수집한 후 task allocation 요청
            self.send_task_allocation_request(allocation_target_task_code, allocation_target_product_code_list, "입고", self.robot_info_list)
            self.product_code_list = []  # list 초기화
            self.robot_info_list = []# list 초기화

        else:
            return


    def send_task_allocation_request(self, task_code, product_code_list, task_type, robot_info_list=None):
        request = AllocatorTask.Request()
        request.task_code = f"Task_{task_code}"
        request.product_code_list = product_code_list
        request.task_type = task_type

        # 로봇 정보를 request에 추가
        if robot_info_list:
            request.robot_name = [str(robot_info.robot_name) for robot_info in robot_info_list]
            request.battery_status = [str(robot_info.battery_status) for robot_info in robot_info_list]
            request.status = [str(robot_info.status) for robot_info in robot_info_list]
            request.estimated_completion_time = [str(robot_info.estimated_completion_time) for robot_info in robot_info_list]


        self.future = self.task_allocator_client.call_async(request)
        self.get_logger().info(f'Sending task allocation request for task_code: task_{task_code} with product_code_list: {product_code_list}')
        self.future.add_done_callback(self.handle_task_allocation_response)

    
    def handle_task_allocation_response(self, future):
        try:
            response = future.result()
            self.get_logger().info(f'Robot Name: {response.robot_name}')
            self.get_logger().info(f'Task Code: {response.task_code}')
            self.get_logger().info(f'Goal Location: {response.rack_list}')
            self.get_logger().info(f'Task Assignment: {response.task_assignment}')
            self.send_task_allocation_results(response.robot_name,response.task_code,response.rack_list,response.task_assignment)

        except Exception as e:
            self.get_logger().error(f'Service call failed: {e}')

    def send_task_allocation_results(self, robot_name,task_code,rack_list,task_assignment):
        allocation_msg = SendAllocationResults()
        allocation_msg.robot_name = robot_name
        allocation_msg.task_code = task_code
        allocation_msg.rack_list= rack_list
        allocation_msg.task_assignment = task_assignment
        self.publisher_allocation_results.publish(allocation_msg)
        
        self.get_logger().info(f'Published task assignment for robot: {robot_name}')

    

class Connect():
    def __init__(self, User, Password):
        self.conn = con.connect(
            # host='database-1.cdigc6umyoh0.ap-northeast-2.rds.amazonaws.com',
            user=User,
            password=Password,
            database='DFC_system_db'
        )
        self.cursor = self.conn.cursor(buffered=True)

    def disConnection(self):
        if self.conn:
            print('!!!!!!DB SHUT DOWN!!!!!!')
            self.conn.close()
            self.cursor.close()
            self.conn = None

# YAML 파일 경로
# yaml_file_path = '/home/edu/dev_ws/git_ws2/ros-repo-4/main_control_server/params/db_user_info.yaml'

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
    
def main(args=None):
    rclpy.init(args=args)
    order_list_service = OrderListService()

    rclpy.spin(order_list_service)
    rclpy.shutdown()

if __name__ == '__main__':
    main()