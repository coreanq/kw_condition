# -*-coding: utf-8 -*-
import inspect
from datetime import datetime
import os
import os.path

def save_log(contents, subject="None", folder=""):
    current_dir = os.getcwd()
    filePath = current_dir + os.sep + folder + os.sep + cur_month() + ".txt"
    openMode = ""
    if (os.path.isfile(filePath)):
        openMode = 'a'
    else:
        openMode = 'w'
    line = '[{0:<8}][{1:<10}] {2}\n'.format(cur_date_time(), subject, contents)

    with open(filePath, openMode, encoding='utf8') as f:
        f.write(line)
    pass

def whoami():
    return '* ' + cur_time_msec() + ' ' + inspect.stack()[1][3] + ' '
    
def whosdaddy():
    return '*' + cur_time_msec() + ' ' + inspect.stack()[2][3] + ' '
    
def cur_date_time(time_string = '%y-%m-%d %H:%M:%S'):
    cur_time = datetime.now().strftime(time_string)
    return cur_time

def cur_time_msec(time_string ='%H:%M:%S.%f'):
    cur_time = datetime.now().strftime(time_string) 
    return cur_time

def cur_date(time_string = '%y-%m-%d'):
    cur_time = datetime.now().strftime(time_string)
    return cur_time

def cur_month(time_string ='%y-%m'):
    cur_time = datetime.now().strftime(time_string)
    return cur_time

def cur_time(time_string ='%H:%M:%S' ):
    cur_time = datetime.now().strftime(time_string)
    return cur_time

if __name__ == "__main__":
    print(cur_time())
    print(cur_date())
    print(cur_date_time() )
    save_log("한글", "한글", "log")