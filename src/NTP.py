import socket
import struct
import time

REF_TIME_1970 = 2208988800  # Reference time
US_POOL_NTP_ADDR = "us.pool.ntp.org"
NTP_PORT = 123
NTP_REQUEST_DATA = b'\x23' + 47 * b'\0' # version 4, client

'''
Returns the time since epoch from an NTP server. Defaults to the US pool.
'''
def get_ntp_time_ms(addr=US_POOL_NTP_ADDR):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        client.sendto(NTP_REQUEST_DATA, (addr, NTP_PORT))
    except (socket.timeout):
        print("NTP socket send timeout")
        return None
    except:
        print("Failed NTP socket send")
        return None

    buf_size = 1024

    try:
        data, address = client.recvfrom(buf_size)
        if data:
            encoded_transmit_timestamp = data[40:48]
            seconds, fraction = struct.unpack("!II", encoded_transmit_timestamp)
            seconds -= REF_TIME_1970
            milliseconds = int(round((seconds + fraction / (2**32))*1000))
            return milliseconds
    except (socket.timeout):
      print("NTP socket read timeout")
    except:
        print("Failed NTP socket read")

        
    return None
    

if __name__ == "__main__":
    print(get_ntp_time_ms())