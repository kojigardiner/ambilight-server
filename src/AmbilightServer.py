import proto.ambilight_pb2 as ambilight_pb2
import socket, time
from enum import Enum
from typing import Dict
import threading

class AmbilightServer:
  # 255.255.255.255 is the default broadcast IP address
  # 3000 is the port the devices will listen to for broadcast messages
  UDP_BROADCAST_IP = "255.255.255.255"
  UDP_BROADCAST_PORT = 3000
  UDP_DATA_PORT = 3001

  # MTU is typically 1472
  MAX_MESSAGE_BYTES = 1460

  '''
  Initialize an AmbilightServer that will broadcast discovery messages at the
  given time interval and waits to receive messages for the given time duration.
  '''
  def __init__(self, discovery_broadcast_ms: int=1000, receive_timeout_ms: int=1000) -> None:
    self.discovery_broadcast_ms = discovery_broadcast_ms
    
    # Setup socket for broadcasting discovery messages
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", 0))
    sock.settimeout(receive_timeout_ms / 1000)
    self.sock_discovery = sock

    # Setup socket for sending data messages
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", 0))
    self.sock_data = sock

    self.clients: Dict[str, ambilight_pb2.Message.Config] = {}

    # Lock to protect the clients list
    self.client_lock = threading.Lock()

    self.discovery_thread = None
    self.sequence_number = 0

  '''
  Sends discovery packets every DISCOVERY_BROADCAST_MS, listens for config 
  packets, and when received, adds the client's information to the client list
  and sends an ACK. Runs in a loop in its own thread.
  '''
  def discovery_broadcast(self):
    while True:
      print("Sending discovery message")
      message = ambilight_pb2.Message()
      message.type = ambilight_pb2.MessageType.DISCOVERY
      message.sender = ambilight_pb2.Sender.SERVER
      self.sock_discovery.sendto(message.SerializeToString(), (self.UDP_BROADCAST_IP, self.UDP_BROADCAST_PORT))

      # Listen for config message
      try:
        data, addr = self.sock_discovery.recvfrom(self.MAX_MESSAGE_BYTES)
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
          self.client_lock.acquire()
          self.clients[f"{client_ip}:{client_port}"] = message.config
          self.client_lock.release()

          print("Sending ack")
          message = ambilight_pb2.Message()
          message.type = ambilight_pb2.MessageType.ACK
          message.sender = ambilight_pb2.Sender.SERVER
          self.sock_discovery.sendto(message.SerializeToString(), (client_ip, client_port))
      except (socket.timeout):
        pass

      time.sleep(self.discovery_broadcast_ms / 1000)

  '''
  Runs the server's discovery broadcast.
  '''
  def run(self):
    if self.discovery_thread is None:
      self.discovery_thread = threading.Thread(target=self.discovery_broadcast)
      self.discovery_thread.start()
    else:
      print("Discovery thread is already running!")
    
  '''
  Sends data to all clients.
  '''
  def send(self, payload: bytes) -> bool:
    if len(self.clients) == 0:
      return False
    
    message = ambilight_pb2.Message()
    message.type = ambilight_pb2.MessageType.DATA
    message.sender = ambilight_pb2.Sender.SERVER
    message.sequence_number = self.sequence_number
    message.timestamp = 2022
    message.data.led_data = payload

    for client, config in self.clients.items():
      print(f"Sending data message to {client}")
      self.sock_data.sendto(message.SerializeToString(), (config.ipv4, config.port))
    
    self.sequence_number += 1

    return True
