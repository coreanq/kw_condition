# -*-coding: utf-8 -*-
import inspect
from datetime import datetime
def whoami():
    return inspect.stack()[1][3]
    
def whosdaddy():
    return inspect.stack()[2][3]
    
def cur_date_time():
    cur_time = datetime.today()
    result = '{}.{:0>2}.{:0>2}-{:0>2}:{:0>2}:{:0>2}.{:0>3}'.format(
        cur_time.year, cur_time.month, cur_time.day,
        cur_time.hour, cur_time.minute, cur_time.second,
        int(cur_time.microsecond/1000))