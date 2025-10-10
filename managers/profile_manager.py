import subprocess

class Profile:
    def __init__(self):
        self.machine_id = self.get_machine_id()
        self.profile_list = ['guest', ]
        
    @classmethod
    def get_machine_id(cls):
        return subprocess.check_output("wmic bios get serialnumber").decode().split()[1]
    
    def as_guest(self):
        return self.machine_id
    
    def add_profile(self, name):
        self.profile_list.append(name)
        