import socket

def send_command(command):
    host = "192.168.2.56"  # ESP32의 IP 주소를 입력하세요
    port = 80

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall(command.encode())
        response = s.recv(1024)
        print("Received:", response.decode())

if __name__ == "__main__":
    commands = [
        "R_A1,O,S\n",
        "R_B3,O,S\n",
        "R_C3,O,S\n"
    ]

    # commands = [
    #     "R_D2,I,S\n",
    #     "R_D1,I,S\n",
    #     "R_D3,I,S\n",
    # ]
        # commands = [
    #     "R_E1,I,S\n",
    #     "R_E3,I,S\n",
    #     "R_B3,I,S\n"
    # ]
    
    # commands = [
    #     "R_D1,I,F\n",
    # # ]
    # commands = [
    #     "R_,O,F\n",
    # ]

    for command in commands:
        send_command(command)

    
    
