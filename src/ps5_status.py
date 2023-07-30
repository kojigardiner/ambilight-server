"""
See https://github.com/iharosi/ps5-wake for the core utility used here.
"""

import TV
import subprocess, json, time

PS5_STATUS_INTERVAL_S = 2     # how often to check the status
STATUS_STANDBY = 620
STATUS_ON = 200

def ps5_status():
    tv = TV.TV()

    last_status = None
    while True:
        time.sleep(PS5_STATUS_INTERVAL_S)

        output = subprocess.run("ps5-wake -jP -B", shell=True, capture_output=True)
        output_str = output.stdout.strip().decode("utf-8")
        print(output_str)
        try:
            d = json.loads(output_str)
        except json.decoder.JSONDecodeError:
            print(f"Could not decode string: {output_str}")
            continue
        status = d["code"]

        if status != STATUS_STANDBY and status != STATUS_ON:
            # unrecognized status
            continue
        if status == last_status:
            # no change
            continue
        
        if status == STATUS_ON:
            # turn on and switch to PS5
            print("PS5 is turning on the TV!")
            if not tv.connect():
                tv.turn_on()
            tv.go_to_ps5()

        elif status == STATUS_STANDBY:
            # switch to apple tv and turn off
            print("PS5 is turning off the TV!")
            tv.go_to_appletv()
            tv.turn_off()

        # update last status
        last_status = status        

if __name__ == "__main__":
    ps5_status()
    print("Exiting")