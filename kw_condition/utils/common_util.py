# -*-coding: utf-8 -*-
import datetime 
import time
from PySide2.QtWidgets import QApplication
from typing import Callable, Union, Any

def process_qt_events(check_flag : Union[Callable[ [], bool], Any], timeout_in_secs: int):
    start_time_stamp = time.time()
    while True:
        time.sleep(0.01)
        QApplication.processEvents()
        end_time_stamp = time.time()

        if( isinstance(check_flag, Callable) ):
            if( check_flag() == True ):
                break

        if( end_time_stamp - start_time_stamp > timeout_in_secs ) :
            print('time out!')
            break

# business day calculate
def date_by_adding_business_days(from_date, add_days):
    business_days_to_add = add_days
    current_date = from_date
    while business_days_to_add > 0:
        current_date += datetime.timedelta(days=1)
        weekday = current_date.weekday()
        if weekday >= 5: # sunday = 6
            continue
        business_days_to_add -= 1
    return current_date

if __name__ == "__main__":
    pass