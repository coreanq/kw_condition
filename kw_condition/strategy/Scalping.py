# -*-coding: utf-8 -
import sys, os, platform, re
from typing import Callable

from PySide2.QtCore import QObject, SIGNAL, Slot, Signal, QStateMachine, QState 
from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QApplication



from kw_condition.backend.KiwoomOpenApiPlus import KiwoomOpenApiPlus
from kw_condition.utils import common_util
from kw_condition.utils import kw_util

import logging
log = logging.getLogger('scalping')

class QuantTrading(QObject):

    sigInitOk = Signal()

    def __init__(self):
        super().__init__()
        self.fsm = QStateMachine()
        self.kw_obj = KiwoomOpenApiPlus()

        self.create_connection()
        self.create_state()
        pass

    def create_connection(self):

        self.kw_obj.sigChejanDataArrived.connect(self.chejan_data_arrived)
        self.kw_obj.sigRealInfoArrived.connect(self.real_info_arrived)

        self.kw_obj.setRealReg('8839', '005930', kw_util.type_fidset['주식체결'] + ';' + kw_util.type_fidset['주식호가잔량'],  '1' )
        pass
        
    def create_state(self):

        # state defintion
        main_state = QState(QState.ParallelStates, self.fsm)       
        base_state = QState(main_state) # 기본 접속 contorl 
        sub_state = QState(main_state) # 추후 기능 추가용 
        tr_state = QState(main_state) # send order 를 제외한 일반적인 조회 TR 용으로 send order 와 일반 조회 TR 의 transation 요청 제한이 다르기 때문에 분리함 
        order_state = QState(main_state)

        self.fsm.setInitialState(main_state)

        base_state.entered.connect( self.base_state_entered )
        # sub_state.entered.connect( self.sub_state_entered )
        # tr_state.entered.connect( self.tr_state_entered )
        # order_state.entered.connect( self.order_state_entered )

        init = QState(base_state)
        disconnected = QState(base_state)
        connected = QState(base_state)
        base_state.setInitialState(init)
        
        # transition defition
        init.addTransition(self.sigInitOk, disconnected)
        disconnected.addTransition(self.kw_obj.sigConnected, connected)
        connected.addTransition(self.kw_obj.sigDisconnected, disconnected)
        
        # state entered slot connect
        init.entered.connect(self.init_entered)
        disconnected.entered.connect(self.disconnected_entered)
        connected.entered.connect(self.connected_entered)


        ###############################################################################################
        #fsm start

        self.fsm.start()
        pass

    @Slot()
    def base_state_entered(self):
        pass

    @Slot()
    def init_entered(self):
        log.debug('')
        self.kw_obj.try_connect()
        self.sigInitOk.emit()
        pass

    @Slot()
    def disconnected_entered(self):
        log.debug('')
            
    @Slot()
    def connected_entered(self):
        log.debug('')
        pass

    @Slot(str, dict)
    def chejan_data_arrived(self):
        log.debug('')
        pass

    @Slot(str, str, list)
    def real_info_arrived(self):
        log.ddebug('')
        pass
    

if __name__ == "__main__":
    myApp = QApplication(sys.argv)
    handler = logging.StreamHandler()
    log.setLevel(logging.DEBUG)

    handler.setFormatter(logging.Formatter( '%(asctime)s [%(levelname)s] %(message)s - %(name)s:%(funcName)s:%(lineno)d' ) )
    log.addHandler( handler ) 

    quant_obj = QuantTrading()



    log.info('done')
    sys.exit(myApp.exec_())
    p