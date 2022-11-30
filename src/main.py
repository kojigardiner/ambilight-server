import time
import AmbilightServer

if __name__ == "__main__":
  server = AmbilightServer.AmbilightServer()
  server.run()
  while True:
    server.send(bytes([128, 50, 32, 128, 0, 0, 0, 128, 0]))
    time.sleep(1/60)