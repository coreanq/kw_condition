# -*-coding: utf-8 -*-
import inspect
from datetime import datetime
import os.path

def save_log(contents, subject="None"):
    fileName = cur_date() + ".txt"
    openMode = ""
    if (os.path.isfile(fileName)):
        openMode = 'a'
    else:
        openMode = 'w'
    line = '[{0:<10}{1:<15}] {2}\n'.format(cur_time(), subject, contents)

    with open(fileName, openMode, encoding='utf8') as f:
        f.write(line)
    pass

def whoami():
    return inspect.stack()[1][3] + ' '
    
def whosdaddy():
    return inspect.stack()[2][3] + ' '
    
def cur_date_time():
    cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return cur_time

def cur_date():
    cur_time = datetime.now().strftime('%Y-%m-%d')
    return cur_time

def cur_time():
    cur_time = datetime.now().strftime('%H:%M:%S')
    return cur_time

if __name__ == "__main__":
    print(cur_time())
    print(cur_date())
    print(cur_date_time() )
    save_log("한글", "한글")