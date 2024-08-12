import random

# 품목 클래스
class Item:
    def __init__(self, item_id, name, quantity):
        self.item_id = item_id
        self.name = name
        self.quantity = quantity
    def __repr__(self):
        return f"Item({self.item_id}, {self.name}, {self.quantity})"

# 수요 예측 데이터를 포함한 OrderList 클래스
class OrderList:
    def __init__(self):
        self.items = self.initialize_items()
        self.demand_forecast = self.initialize_demand_forecast()
        
    def initialize_items(self):
        # 18개의 품목 초기화
        items = [
            # Item('P01', "Toothpaste", random.randint(1, 100)), ##R_A1
            # Item('P02', "Shampoo", 0),
            # Item('P03', "Soap", random.randint(1, 100)), ##R_A3
            # Item('P04', "Hand Sanitizer", random.randint(1, 100)), ##R_B1 LED X
            # Item('P05', "Laundry Detergent", random.randint(1, 100)), ##R_B2
            # Item('P06', "Dish Soap", 0), ##R_B3
            # Item('P07', "Paper Towels", random.randint(1, 100)), ##R_C1
            # Item('P08', "Toilet Paper", random.randint(1, 100)), ##R_C2
            # Item('P09', "Facial Tissues", random.randint(1, 100)), ##R_C3
            Item('P10', "Trash Bags", 0), ##R_D1
            Item('P11', "Sponges", 0), ##R_D2
            Item('P12', "Cleaning Spray", 0), ##R_D3
            Item('P13', "Batteries", 0), ##R_E1
            # Item('P14', "Light Bulbs", random.randint(1, 100)), ##R_E2
            Item('P15', "Umbrella", 0), ##R_E3
            # Item('P16', "Notebook", random.randint(1, 100)), ##R_F1
            # Item('P17', "Pen", 0), ##R_F2
            Item('P18', "Basketball", 0) ##R_F3
        ]
        return items
    
    def initialize_demand_forecast(self):
        # 수요 예측 데이터를 초기화
        demand_forecast = {
            'P02': random.randint(20, 70),
            'P06': random.randint(10, 50),
            'P10': random.randint(15, 60),
            'P11': random.randint(5, 40),
            'P12': random.randint(10, 55),
            'P13': random.randint(25, 75),
            'P15': random.randint(5, 30),
            'P17': random.randint(10, 45),
            'P18': random.randint(20, 50)
        }
        return demand_forecast

    def get_random_order_list(self):
        # 6개의 랜덤 품목 선택
        num_items = random.randint(6, 6)
        random_items = random.sample(self.items, num_items)
        # 선택된 품목의 수량을 수요 예측 데이터를 기반으로 설정
        for item in random_items:
            item.quantity = self.demand_forecast.get(item.item_id, random.randint(1, 50))
        return random_items
    
    def print_order_list(self, order_list):
        for item in order_list:
            print(f"Item ID: {item.item_id}, Name: {item.name}, Quantity: {item.quantity}")
        print(f"Total items: {len(order_list)}")  # 출력된 항목의 개수를 출력

# OrderList 인스턴스 생성 및 주문 목록 생성 및 출력
order_list_instance = OrderList()
random_order_list = order_list_instance.get_random_order_list()
order_list_instance.print_order_list(random_order_list)
