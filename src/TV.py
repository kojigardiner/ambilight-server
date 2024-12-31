from pywebostv.controls import MediaControl, SystemControl, ApplicationControl, InputControl, TvControl, SourceControl
from pywebostv.connection import WebOSClient
import json, time, os, socket, binascii

TV_CREDS_FILE = "/home/pi/repos/ambilight-server/src/tv_creds.json"
BLANK_URL = "https://www.blank.org/"

# Wake-on-LAN
WOL_BROADCAST_ADDR = '255.255.255.255'
WOL_BROADCAST_PORT = 7
PING_TIMEOUT_S = 1
WOL_TIMEOUT_S = 10
WOL_PING_TIMEOUT_S = 30

class TV:
    def __init__(self):
        self.client = None
        self._reset_controls()
        self.creds = self._read_creds()
        self.connect()

    def _reset_controls(self):
        """
        Resets all controls.
        """
        self.media = None
        self.system = None
        self.app = None
        self.inp = None
        self.tv_control = None
        self.source_control = None
        self.last_source = None
        self.sources = None

    def _read_creds(self):
        try:
            with open(TV_CREDS_FILE, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"{TV_CREDS_FILE} not found, will be written on first connect()")
            return {}

        return data
    
    def _write_creds(self, creds):
        with open(TV_CREDS_FILE, "w") as f:
            json.dump(creds, f)

    def _init_controls(self) -> bool:
        """
        Initializes all controls. Returns True if successful, False if any controls
        fail to init.
        """
        if not self.client:
            return False

        self.media = MediaControl(self.client)
        self.system = SystemControl(self.client)
        self.app = ApplicationControl(self.client)
        self.inp = InputControl(self.client)
        self.tv_control = TvControl(self.client)
        self.source_control = SourceControl(self.client)
    
        if not self.media or not self.system or not self.app \
        or not self.inp or not self.tv_control or not self.source_control:
            print("Failed to initialize a control!")
            self._reset_controls()
            return False
        
        self.sources = self.source_control.list_sources()

        return True

    def _get_current_source(self):
        curr_app_id = self.app.get_current()
        for s in self.sources:
            if s["appId"] == curr_app_id:
                return s
        return None

    def _go_to_source(self, name):
        self.last_source = self._get_current_source()
        for s in self.sources:
            if s.label == name:
                print(f"Setting source to {s}")
                self.source_control.set_source(s)
                return True
        return False

    def _launch_browser(self, url):
        if not self.client or not self.app:
            return
        
        apps = self.app.list_apps()
        match = [x for x in apps if "web browser" in x["title"].lower()]
        if len(match) < 1:
            return
        
        browser = match[0]

        launch_info = self.app.launch(browser, content_id=url)

    def _click_browser_fullscreen(self):
        if not self.client or not self.inp:
            return

        self.inp.connect_input()

        # move to the upper right
        for i in range(200):
            self.inp.move(100, -100)
        time.sleep(0.2)

        # shift to the full screen button
        for i in range(3):
            self.inp.move(-100, 0)
        time.sleep(0.2)

        self.inp.move(0, 100)
        time.sleep(1)

        # click it
        self.inp.click()

        self.inp.disconnect_input()

    def connect(self):
        if self.creds.get("ip"):
            self.client = WebOSClient(self.creds["ip"])
            if not self.is_on():
                print("TV is not on! Try turning it on manually with turn_on()")
                return False
        else:
            print("Discovering TV...")
            discovered = WebOSClient.discover()
        
            if not discovered or len(discovered) < 1:
                self.client = None
                return False
            else:
                print(f"Found {len(discovered)} clients")
                self.client = discovered[0]
                #print(f"Connecting to client at {self.client.local_address[0]}:{self.client.local_address[1]}")

        print(f"Connecting to client at {self.client.host}:{self.client.port}")
        self.creds["ip"] = self.client.host

        while True:
            try:
                self.client.connect()
                break
            except ConnectionRefusedError:
                print("Failed to connect, trying again...")
                pass

        for status in self.client.register(self.creds):
            if status == WebOSClient.PROMPTED:
                    print("Please accept the connect on the TV!")
            elif status == WebOSClient.REGISTERED:
                    print("Registration successful!")
        
        self._init_controls()
        self.creds["mac"] = self.system.info()["device_id"]

        self._write_creds(self.creds)

        return True

    def show_white_screen(self):
        if self.connect():
            self.last_source = self._get_current_source()
            self._launch_browser(BLANK_URL)
            self._click_browser_fullscreen()

    def go_to_last_source(self):
        if self.connect():
            tmp = self._get_current_source()
            if self.last_source:
                self.source_control.set_source(self.last_source)
                self.last_source = tmp

    def go_to_appletv(self):
        if self.connect():
            self._go_to_source("Apple TV")
    
    def go_to_ps5(self):
        if self.connect():
            self._go_to_source("PS5")

    def turn_on(self):
        print("Attempting to turn on with WOL...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        sock.settimeout(WOL_TIMEOUT_S)
        
        mac_bin = binascii.unhexlify(self.creds["mac"].replace(":",""))
        magic = b'\xff'*6 + mac_bin*16

        sock.sendto(magic, (WOL_BROADCAST_ADDR, WOL_BROADCAST_PORT))

        for i in range((int)(WOL_PING_TIMEOUT_S / PING_TIMEOUT_S)):
            if self.is_on():
                print("Successfully turned on using WOL!")
                return self.connect()
        print("Failed to turn on using WOL!")
        return False

    def is_on(self):
        return (os.system(f"ping -w {PING_TIMEOUT_S} -c 1 " + self.creds["ip"]) == 0)
    
    def turn_off(self):
        if self.connect():
            print("Turning off...")
            self.system.power_off()