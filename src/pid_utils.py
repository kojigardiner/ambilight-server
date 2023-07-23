import os, signal

PID_DIR = "/home/pi/scripts/Ambilight/.pid"

def check_pid(pid):        
    """ Check For the existence of a unix pid. """
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

def update_pid_file(pid_filename):    
    pid_filepath = os.path.join(PID_DIR, pid_filename)
    
    print(f"pid_filepath: {pid_filepath}")

    if os.path.exists(pid_filepath):
        with open(pid_filepath) as f:
            try:
                last_pid = int(f.readline())
                if check_pid(last_pid):
                    print(f"PID {last_pid} is running, killing it...",end="")
                    os.kill(last_pid, signal.SIGKILL)
                    print("done")
            except ValueError:  # catch the case where the file exists but is empty or malformed
                pass
    
    curr_pid = os.getpid()
    with open(pid_filepath, 'w') as f:
        print(f"Creating file with PID {curr_pid}")
        f.write(str(curr_pid))