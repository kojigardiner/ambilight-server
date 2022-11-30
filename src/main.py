import proto.ambilight_pb2 as ambilight_pb2
import socket, select, time
from enum import Enum

# We send the discovery message every so often
DISCOVERY_BROADCAST_MS = 1000

# 255.255.255.255 is the default broadcast IP address
# 3000 is the port the devices will listen to for broadcast messages
UDP_BROADCAST_IP = "255.255.255.255"
UDP_BROADCAST_PORT = 3000

LOCAL_IP = "0.0.0.0"
LOCAL_PORT = 12345

MAX_MESSAGE_BYTES = 1460

# State machine states
class State(Enum):
  DISCOVERY = 0
  DATA = 1

''' 
Sets up a UDP socket and returns it.
'''
def init_udp_socket() -> socket.socket:
  # Make sure to set the SO_BROADCAST option or else broadcasts will fail
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
  
  host = socket.gethostbyname(socket.gethostname())
  sock.bind((LOCAL_IP, LOCAL_PORT))
  sock.settimeout(1)

  return sock

'''
Runs the server state machine with a given initial state and a UDP socket
'''
def run_server(sock: socket.socket):
  state = State.DISCOVERY
  sequence_number = 1
  clients = []

  while True:
    # State: DISCOVERY

    # Behavior: Start DISCOVERY_MS timer. Send discovery packets every 
    # DISCOVERY_BROADCAST_MS. Listen for config packets, and when received, add 
    # client's information to dictionary and send ACK.

    # Transition: On timeout, transition to DATA state.
    if state == State.DISCOVERY:
      # Send discovery message
      print("Sending discovery message")
      message = ambilight_pb2.Message()
      message.type = ambilight_pb2.MessageType.DISCOVERY
      message.sender = ambilight_pb2.Sender.SERVER
      message.sequence_number = sequence_number
      message.timestamp = 2022
      sock.sendto(message.SerializeToString(), (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))

      # Listen for config message
      try:
        data, addr = sock.recvfrom(MAX_MESSAGE_BYTES)
        print(f"Received: {data}")
        if (len(data) > 0):
          message.ParseFromString(data)
          print(f"Type: {message.type}")
          print(f"Sender: {message.sender}")
          client_ip = message.config.ipv4
          client_port = message.config.port
          print(f"IP: {client_ip}")
          print(f"Port: {client_port}")

          print("Adding client")
          clients.append(message.config)


          print("Sending ack")
          message = ambilight_pb2.Message()
          message.type = ambilight_pb2.MessageType.ACK
          message.sender = ambilight_pb2.Sender.SERVER
          message.sequence_number = sequence_number
          message.timestamp = 2022
          sock.sendto(message.SerializeToString(), (client_ip, client_port))

          print("Transition: DISCOVERY ==> DATA")
          state = State.DATA
      except (socket.timeout):
        pass

      time.sleep(DISCOVERY_BROADCAST_MS / 1000)
    # State: DATA
  
    # Behavior: If data is available, send it to all clients.

    # Transition: None
    elif state == State.DATA:
      print("Sending data message")
      message = ambilight_pb2.Message()
      message.type = ambilight_pb2.MessageType.DATA
      message.sender = ambilight_pb2.Sender.SERVER
      message.sequence_number = sequence_number
      message.timestamp = 2022
      message.data.led_data = bytes([128, 50, 32, 128, 0, 0, 0, 128, 0])

      for client in clients:
        sock.sendto(message.SerializeToString(), (client.ipv4, client.port))
      
      sequence_number += 1

      time.sleep(1/60)
    else:
      print(f"State {state} not recognized!")

if __name__ == "__main__":
  sock = init_udp_socket()
  run_server(sock)