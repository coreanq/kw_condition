# -*-coding: utf-8 -*-
import inspect
from datetime import datetime
def whoami():
    return inspect.stack()[1][3] + ' '
    
def whosdaddy():
    return inspect.stack()[2][3] + ' '
    
def cur_date_time():
    cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S ')
    return cur_time

if __name__ == "__main__":
    print(cur_date_time() )