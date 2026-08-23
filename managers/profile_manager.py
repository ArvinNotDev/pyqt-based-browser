import subprocess
import platform
import hashlib

class Profile:
    def __init__(self):
        self.machine_id = self.get_machine_id()
        self.profile_list = ['guest', ]
        
    @classmethod
    def get_machine_id(cls):
        """Get a unique machine identifier. Works on Windows, Linux, and macOS."""
        system = platform.system()
        try:
            if system == "Windows":
                return subprocess.check_output("wmic bios get serialnumber", shell=True).decode().split()[1]
            elif system == "Darwin":
                return subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { print $3 }'", shell=True).decode().strip().strip('"')
            else:  # Linux
                return subprocess.check_output("cat /etc/machine-id 2>/dev/null || dbus-machine-id", shell=True).decode().strip()
        except Exception:
            # Fallback: generate a hash based on hostname + username
            import getpass, socket
            fallback = f"{socket.gethostname()}-{getpass.getuser()}"
            return hashlib.sha256(fallback.encode()).hexdigest()
    
    def as_guest(self):
        return self.machine_id
    
    def add_profile(self, name):
        self.profile_list.append(name)
        