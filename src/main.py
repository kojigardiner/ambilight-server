import proto.ambilight_pb2 as ambilight_pb2
import socket, time

example = ambilight_pb2.Example()
UDP_IP = "ambilight-client.local"
UDP_PORT = 2390
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

i = 0
while True:
  example.type = i
  example.name = "Koji Gardiner"
  MESSAGE = example.SerializeToString()
  print(f"message = {MESSAGE}")
  sock.sendto(MESSAGE, (UDP_IP, UDP_PORT))
  i += 1
  time.sleep(1)