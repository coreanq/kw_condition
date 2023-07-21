user_id = ''
user_pass= '' 
user_cert = ''

import sys, os, platform, re

from PySide2.QtCore import QObject, SIGNAL, Slot, Signal, QStateMachine, QState, QHistoryState, QTimer
from PySide2.QtWidgets import *


import pywinauto
from pywinauto.application import Application
import pandas as pd

import logging
log = logging.getLogger('kw')


################################################################################################################################
# 업그레이드 확인 창 처리 
# try:
#     app = Application(backend="uia").connect( path = 'C:/KiwoomEasy/bin/nkeasyversionup.exe.exe', timeout = 120 )
#     # find dialog
#     main_dlg = app.확인
#     main_dlg.click_input( button = 'left' )
#     pass
# except Exception as e:
#     print( e ) 
#     pass

# while True:

#     try:
#         # 뉴스 탭 클릭 
#         main_dlg.뉴스TabIItem.click_input( button = 'left')

#         # 전체 라디오 박스 클릭 
#         main_dlg.전체Button.click_input( button = 'left')

#         # 마우스 우클릭 해서 context 메뉴 보이고
#         main_dlg.click_input( button = 'right')

#         # 'z' 키 눌러서 클립보드 복사 
#         # target_window.type_keys('z')

#         app.컨텍스트Menu['복사'].click_input()
#         # app.PopupMenu.wait('ready').Menu().get_menu_path('복사(Z)')[0].click_input()

#     except Exception as e:
#         print( e ) 
#         continue
#     else:
#         try:
#             df = pd.read_clipboard()

#             df = df.dropna( subset = ['CODE'] ).reset_index() 
#             code_list = df[['CODE']].values.tolist()

#             # print('') 
#             # print('') 
#             # print( code_list )
#             # print('') 

#             result_list = []
#             for item in code_list:  
#                 item[0] = item[0][1:] # 첫 ' 시작 제거 
#                 parsed_item = item[0].split('/')
#                 result_list.extend( parsed_item) 

#             print( result_list ) 
#         except Exception as e:
#             print( e ) 


class KiwoomEasyNewsCrawler(QMainWindow):

    sigComplete = Signal()
    sigError = Signal()
    sigRetry = Signal()

    sigStop = Signal()
    sigResume = Signal()

    def __init__(self):
        super().__init__()
        self.fsm = QStateMachine()

        self.app = None
        self.main_dlg = None
        self.target_pane = None

        self.main_widget = QWidget()

        self.main_layout = QHBoxLayout(self.main_widget)

        self.run_button = QPushButton('Run') 
        self.stop_button = QPushButton('Stop') 

        self.main_layout.addWidget( self.run_button )
        self.main_layout.addWidget( self.stop_button )

        self.setCentralWidget(self.main_widget)

        self.create_connection()
        self.create_state()


    def create_connection(self):
        self.run_button.clicked[bool].connect(self.sigResume )
        self.stop_button.clicked[bool].connect(self.sigStop )
        pass

        
    def create_state(self):

        # state defintion
        main_state = QState(self.fsm)       
        stopped_state = QState(self.fsm)

        main_history_state = QHistoryState(main_state)

        start_main_app_state = QState(main_state) 
        login_main_app_state = QState(main_state)

        connect_version_up_state = QState(main_state)
        check_out_version_up_state = QState(main_state)

        connect_main_app_state = QState(main_state)
        run_macro_state = QState(main_state)


        self.fsm.setInitialState(main_state)

        main_state.entered.connect( self.main_entered )

        main_state.setInitialState( start_main_app_state )

        stopped_state.entered.connect( self.stopped_entered )

        start_main_app_state.entered.connect( self.start_main_app_entered )
        login_main_app_state.entered.connect( self.login_main_app_entered )

        connect_version_up_state.entered.connect( self.connect_version_up_entered )
        check_out_version_up_state.entered.connect( self.check_out_version_up_entered )

        connect_main_app_state.entered.connect( self.connect_main_app_entered )
        run_macro_state.entered.connect( self.run_macro_entered )


        stopped_state.addTransition( self.sigResume, main_history_state )

        start_main_app_state.addTransition( self.sigComplete, login_main_app_state )
        start_main_app_state.addTransition( self.sigRetry, start_main_app_state )
        start_main_app_state.addTransition( self.sigStop, stopped_state )

        login_main_app_state.addTransition( self.sigComplete, connect_version_up_state )
        login_main_app_state.addTransition( self.sigRetry, login_main_app_state )
        login_main_app_state.addTransition( self.sigStop, stopped_state)

        connect_version_up_state.addTransition( self.sigComplete, check_out_version_up_state )
        connect_version_up_state.addTransition( self.sigRetry, connect_version_up_state )
        connect_version_up_state.addTransition( self.sigStop, stopped_state )

        check_out_version_up_state.addTransition( self.sigComplete, connect_main_app_state )
        check_out_version_up_state.addTransition( self.sigRetry, check_out_version_up_state )
        check_out_version_up_state.addTransition( self.sigStop, stopped_state )

        connect_main_app_state.addTransition( self.sigComplete, run_macro_state )
        connect_main_app_state.addTransition( self.sigRetry, connect_main_app_state )
        connect_main_app_state.addTransition( self.sigStop, stopped_state )

        run_macro_state.addTransition(self.sigStop, stopped_state )
        run_macro_state.addTransition(self.sigRetry, run_macro_state )

        #fsm start
        self.fsm.start()
        pass

    def main_entered(self):
        log.debug('')
        pass

    def stopped_entered(self):
        log.debug('')
        pass
    def start_main_app_entered(self):
        log.debug('')

        # 키움 easy stater 실행         
        try:
            self.app = Application(backend="uia").start('C:/KiwoomEasy/bin/nkeasystarter.exe', timeout = 0.1)
        except:
            self.sigRetry.emit()
            return
        self.sigComplete.emit()
        pass

    def login_main_app_entered(self):
        log.debug('')

        # find dialog
        main_dlg = self.app.window( best_match= '영웅문 EASY Login')

        try: 
            main_dlg.wait( wait_for = 'exists', timeout=0.1 ) # memory 에 valid 한 데이터가 들어갈때까지 기다림 
            pass
        except pywinauto.timings.TimeoutError:
            QTimer.singleShot( 100, self.sigRetry )
            return
        except Exception as e:
            log.debug(e)
            QTimer.singleShot( 100, self.sigRetry )
            return
        # 이작업을 통해 타겟이 되는 컨트롤을 찾아야 함 
        # main_dlg.print_control_identifiers()

        edit_controls = [ main_dlg.Edit1, main_dlg.Edit2, main_dlg.Edit3 ]
        user_inputs = [user_id, user_pass, user_cert]

        for infos in zip(edit_controls, user_inputs):
            child_control = infos[0]
            child_control.double_click_input( button = 'left' ) # 더블클릭으로 기존 입력을 selecting 해서 지워지게 함 
            child_control.type_keys( infos[1] ) # shoule use instead of set_text 

        login_btn_control = main_dlg.Button1
        login_btn_control.click_input( button = 'left' )

        self.sigComplete.emit()

        pass
    
    def connect_version_up_entered(self):
        log.debug('')
        self.sigComplete.emit()
        pass

    def check_out_version_up_entered(self):
        log.debug('')

        try:
            self.app = Application(backend="uia").connect( path = 'C:/KiwoomEasy/bin/nkeasy.exe', timeout = 0.1 )
        except:
            self.sigRetry.emit()
            return
        self.sigComplete.emit()

        pass

    def connect_main_app_entered(self):
        log.debug('')

        # find dialog
        self.main_dlg = self.app.window( best_match = '영웅문EASY' )

        try: 
            self.main_dlg.wait( wait_for = 'exists', timeout=0.1 ) # memory 에 valid 한 데이터가 들어갈때까지 기다림 
            pass
        except pywinauto.timings.TimeoutError:
            QTimer.singleShot( 100, self.sigRetry )
        except Exception as e:
            log.debug(e)
            QTimer.singleShot( 100, self.sigRetry )
            return

        # self.main_dlg.print_control_identifiers()

        # 우하단 패널 
        self.target_pane = self.main_dlg.Pane33
        # target_window.print_control_identifiers()

        self.sigComplete.emit()

        pass

    def run_macro_entered(self):
        log.debug('')

        try:
            # 뉴스 탭 클릭 
            self.main_dlg.뉴스TabIItem.click_input( button = 'left')

            # 전체 라디오 박스 클릭 
            self.main_dlg.전체Button.click_input( button = 'left')

            # 마우스 우클릭 해서 context 메뉴 보이고
            self.target_pane.click_input( button = 'right')
            self.app.컨텍스트Menu['복사'].click_input()

        except Exception as e:
            log.debug(e)

        QTimer.singleShot(5000, self.sigRetry )

        pass


if __name__ == "__main__":
    log = logging.getLogger('kw')
    handler = logging.StreamHandler()
    log.setLevel(logging.DEBUG)

    handler.setFormatter(logging.Formatter( '%(asctime)s [%(levelname)s] %(message)s - %(name)s:%(funcName)s:%(lineno)d' ) )
    log.addHandler( handler ) 

    myApp = QApplication(sys.argv)

    main_window = KiwoomEasyNewsCrawler()
    main_window.show()

    sys.exit(myApp.exec_())
