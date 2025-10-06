import subprocess
from bcrypt import hashpw, checkpw, gensalt

class Profile:
    def __init__(self):
        self.machine_id = self.get_machine_id()
        

    @classmethod
    def get_machine_id(cls):
        return subprocess.check_output("wmic bios get serialnumber").decode().split()[1]