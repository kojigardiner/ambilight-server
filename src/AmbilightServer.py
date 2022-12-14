import proto.ambilight_pb2 as ambilight_pb2
import socket, time
from enum import Enum
from typing import Dict, Tuple
import threading
import NTP

class AmbilightServer:
  # 255.255.255.255 is the default broadcast IP address
  # 3000 is the port the devices will listen to for broadcast messages
  UDP_BROADCAST_IP = "255.255.255.255"
  UDP_BROADCAST_PORT = 3000
  UDP_DATA_PORT = 3001
  NTP_PERIOD_MS = 5000
  ALL_CLIENTS = (0,0)

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
    sock.settimeout(receive_timeout_ms / 1000)
    self.sock_data = sock

    self.clients: Dict[str, ambilight_pb2.Message.Config] = {}

    # Lock to protect the clients list
    self.client_lock = threading.Lock()

    self.discovery_thread = None
    self.ntp_thread = None

    # Lock to protect time variables
    self.ntp_lock = threading.Lock()
    self.ntp_time_ms = -1
    self.perf_counter_at_last_ntp = -1
    self.sequence_number = 0

  '''
  Gets time from the NTP server and updates member variables.
  '''
  def update_time(self):
    while True:
      print("Getting NTP time")
      latest_ntp_time_ms = NTP.get_ntp_time_ms()
      
      self.ntp_lock.acquire()
      self.ntp_time_ms = latest_ntp_time_ms
      self.perf_counter_at_last_ntp = time.perf_counter()
      self.ntp_lock.release()

      time.sleep(self.NTP_PERIOD_MS)


  '''
  Sends discovery packets every DISCOVERY_BROADCAST_MS, listens for config 
  packets, and when received, adds the client's information to the client list
  and sends an ACK. Runs in a loop in its own thread.
  '''
  def discovery_broadcast(self):
    while True:
      message = ambilight_pb2.Message()
      print("Sending discovery message")
      self.send(ambilight_pb2.MessageType.DISCOVERY, (self.UDP_BROADCAST_IP, self.UDP_BROADCAST_PORT))

      # Listen for messages on the discovery port and the data port
      try:
        data, addr = self.sock_discovery.recvfrom(self.MAX_MESSAGE_BYTES)
        if (len(data) > 0):
          message.ParseFromString(data)
          if message.type == ambilight_pb2.MessageType.CONFIG:
            print(f"Received config message")
            client_ip = message.config.ipv4
            client_port = message.config.port
            print(f"Adding client {client_ip}:{client_port}")
            
            self.client_lock.acquire()
            self.clients[self.addr_to_str((client_ip, client_port))] = message.config
            self.client_lock.release()

            print("Sending config ack")
            self.send(ambilight_pb2.MessageType.ACK_DISCOVERY, (client_ip, client_port))
          if message.type == ambilight_pb2.MessageType.HEARTBEAT:
            print("Sending heartbeat ack")
            self.send(ambilight_pb2.MessageType.ACK_HEARTBEAT, (client_ip, client_port))
      except (socket.timeout):
        print("Socket read timeout")
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
    if self.ntp_thread is None:
      self.ntp_thread = threading.Thread(target=self.update_time)
      self.ntp_thread.start()
    else:
      print("NTP thread is already running!")  
  
  '''
  Sends a message. If the to_client field is empty, defaults to sending the
  message to all clients. 
  '''
  def send(self, type: ambilight_pb2.MessageType, to_client: Tuple[str, int]=ALL_CLIENTS, payload: bytes=b"") -> bool:
    message = ambilight_pb2.Message()
    message.type = type
    message.sender = ambilight_pb2.Sender.SERVER
    message.sequence_number = self.sequence_number

    if type == ambilight_pb2.MessageType.DATA:
      message.data.led_data = payload

    if to_client == self.ALL_CLIENTS:
      for client, config in self.clients.items():
        self.send_message_with_timestamp(message, (config.ipv4, config.port))
    else:
      self.send_message_with_timestamp(message, to_client)
    
    return True

  '''
  Computes a timestamp and sends the message with it.
  '''
  def send_message_with_timestamp(self, message, ip_and_port):
    if message.type == ambilight_pb2.MessageType.DISCOVERY or message.type == ambilight_pb2.MessageType.ACK_DISCOVERY:
      sock = self.sock_discovery
    else:
      sock = self.sock_data

    self.ntp_lock.acquire()
    message.timestamp = int(round(self.ntp_time_ms + (time.perf_counter() - self.perf_counter_at_last_ntp)*1000))
    self.ntp_lock.release()
    sock.sendto(message.SerializeToString(), ip_and_port)
    print(f"Sending message to {self.addr_to_str(ip_and_port)} at {message.timestamp}")
    self.sequence_number += 1

  '''
  Returns the string representation of a (ipv4, port) tuple as "ipv4:port".
  '''
  def addr_to_str(self, addr: Tuple[str, int]) -> str:
    return f"{addr[0]}:{addr[1]}"