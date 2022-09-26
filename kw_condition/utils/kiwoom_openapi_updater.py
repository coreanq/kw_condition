user_id = ''
user_pass= '' 
user_cert = ''

import sys, os
from PySide2.QtWidgets import *
from PySide2.QtAxContainer import *
import pythoncom
import time
import multiprocessing as mp

from PySide2.QtCore import SIGNAL



'''
아래 에러 해결 방법
QWindowsContext: OleInitialize() failed:  "COM error 0x80010106 RPC_E_CHANGED_MODE (Unknown error 0x080010106)"

발생원인
pywinauto 와 PyQt5 를 같이 import 하는 경우 발생

해결방법
pywinauto import 하는 곳 보다 더 빠른곳에 아래 코드 넣도록 한다.

import sys
import warnings
warnings.simplefilter("ignore", UserWarning)
sys.coinit_flags = 2
'''

import warnings
warnings.simplefilter("ignore", UserWarning)
sys.coinit_flags = 2
from pywinauto.application import Application


#--------------------------------------------------------------------
# 로그인창
#--------------------------------------------------------------------
class LoginWindow(QWidget):
    app = QApplication(sys.argv)

    def __init__(self):
        super().__init__()
        self.login_status = False
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.connect( SIGNAL( "OnEventConnect(int)"), self._OnEventConnect )

        self.login()

    def login(self):
        self.ocx.dynamicCall("CommConnect()")
        while not self.login_status: 
            pythoncom.PumpWaitingMessages()
            time.sleep(0.001)

    def _OnEventConnect(self, err_code):
        self.login_status = True

#--------------------------------------------------------------------
# 자동 로그인 해제 및 설정
#--------------------------------------------------------------------
LOGIN_FILE     = "C:/OpenAPI/system/Autologin.dat"
LOGIN_FILE_TMP = "C:/OpenAPI/system/Autologin.tmp"


def turn_off_auto():
    if os.path.isfile(LOGIN_FILE):
        os.rename(LOGIN_FILE, LOGIN_FILE_TMP) 

def turn_on_auto():
    if os.path.isfile(LOGIN_FILE_TMP):
        os.rename(LOGIN_FILE_TMP, LOGIN_FILE)


# 키움 updater 실행 
def version_up():    

    sub_proc = mp.Process(target=LoginWindow, name="Sub Process", daemon=True)
    sub_proc.start()

    # 키움 openapi stater 
    app = Application(backend="uia").connect( path = 'C:/OpenAPI/opstarter.exe', timeout = 20)

    # find dialog
    main_dlg = app.window( best_match= 'Open API Login')
    main_dlg.wait( wait_for = 'exists' ) # memory 에 valid 한 데이터가 들어갈때까지 기다림 

    # 이작업을 통해 타겟이 되는 컨트롤을 찾아야 함 
    # main_dlg.print_control_identifiers()

    edit_controls = [ main_dlg.Edit, main_dlg.Edit2, main_dlg.Edit3 ]
    user_inputs = [user_id, user_pass, user_cert]

    for infos in zip(edit_controls, user_inputs):
        child_control = infos[0]
        child_control.double_click_input( button = 'left' ) # 더블클릭으로 기존 입력을 selecting 해서 지워지게 함 
        child_control.type_keys( infos[1] ) # shoule use instead of set_text 

    login_btn_control = main_dlg.Button1
    login_btn_control.click_input( button = 'left' )

    ################################################################################################################################
    # 버전업 처리 종료 경고 창 
    try:
        popup_dlg = main_dlg.window( best_match= 'opstarter' )
        popup_dlg.wait( wait_for = 'visible', timeout= 120 ) 

        # 이작업을 통해 타겟이 되는 컨트롤을 찾아야 함 
        # popup_dlg.print_control_identifiers()

        # process kill
        while sub_proc.is_alive():
            sub_proc.kill()
            time.sleep(1)

        popup_dlg.확인Button.click_input( button = 'left' )
        pass
    except Exception as e:
        print( e ) 
        pass

    ################################################################################################################################
    # 업그레이드 확인 창 처리 
    try:
        app = Application(backend="uia").connect( path = 'C:/OpenAPI/opversionup.exe.exe', timeout = 30 )
        # find dialog
        main_dlg = app.window( best_match= '업그레이드 확인' )
        main_dlg.wait( wait_for = 'exists' ) # memory 에 valid 한 데이터가 들어갈때까지 기다림 

        # 이작업을 통해 타겟이 되는 컨트롤을 찾아야 함 
        main_dlg.print_control_identifiers()

        main_dlg.확인Button.click_input( button = 'left' )

        print("upgrade done")
        sys.exit()
        pass
    except Exception as e:
        print( e ) 
        pass

    print("nothing to upgrade")

if __name__ == '__main__':
    turn_off_auto()
    version_up()
    turn_on_auto()
    pass
