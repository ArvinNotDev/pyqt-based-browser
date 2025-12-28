"""
Set http proxy to the os system
handle windows linux system first diagnose and set
"""

import os
import platform
from PySide6.QtWebEngineCore import QWebEngineProfile
import os
import logging
logger = logging.getLogger(__name__)


class Os:
    Windows = "Windows"
    Linux = "Linux"

def get_os_name():
    return platform.system()    

    
action_list = ["set", "clear"]


def set_proxy(profile: QWebEngineProfile, host: str, port: int):
    pass
def clear_proxy(profile: QWebEngineProfile):
    pass
def manage_proxy(profile, host, port, action="set"):
  
    if action == action_list[0]:
        set_proxy(profile, host, port)
    elif action == action_list[1]:
        clear_proxy(profile)
    


