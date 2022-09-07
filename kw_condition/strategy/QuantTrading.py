# -*-coding: utf-8 -
import sys, os, platform, re
from typing import Callable

from PySide2.QtCore import QObject, SIGNAL, Slot, Signal, QStateMachine, QState 
from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QApplication
from PySide2.QtAxContainer import QAxWidget

from kw_condition.utils import common_util
from kw_condition.utils import kw_util


import logging
log = logging.getLogger('quanting')

class QuantTrading(QObject):

    def __init__(self):
        super().__init__()
        pass

        # self.currentTime = datetime.datetime.now()

    def create_connection(self):
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
        sub_state.entered.connect( self.sub_state_entered )
        tr_state.entered.connect( self.tr_state_entered )
        order_state.entered.connect( self.order_state_entered )

        init = QState(base_state)
        disconnected = QState(base_state)
        connected = QState(base_state)
        base_state.setInitialState(init)
        
        # transition defition
        init.addTransition(self.sigInitOk, disconnected)
        disconnected.addTransition(self.sigConnected, connected)
        disconnected.addTransition(self.sigTryConnect, disconnected)
        connected.addTransition(self.sigDisconnected, disconnected)
        
        # state entered slot connect
        init.entered.connect(self.init_entered)
        disconnected.entered.connect(self.disconnected_entered)
        connected.entered.connect(self.connected_entered)


        ###############################################################################################
        # sub parallel state define (TR)
        tr_init = QState(tr_state)
        tr_standby = QState(tr_state)
        tr_waiting = QState(tr_state)

        tr_state.setInitialState(tr_init)

        tr_init.addTransition(self.sigConnected, tr_standby )
        tr_standby.addTransition(self.sigRequestTR, tr_waiting )
        tr_waiting.addTransition(self.sigTRWaitingComplete, tr_standby )
        tr_waiting.addTransition(self.sigTRResponseError, tr_standby )

        # state entered slot connect
        tr_init.entered.connect(self.tr_init_entered)
        tr_standby.entered.connect(self.tr_standby_entered)
        tr_waiting.entered.connect(self.tr_waiting_entered)

        ###############################################################################################
        # order state parallel state define (TR)
        order_init = QState(order_state)
        order_standby = QState(order_state)
        order_waiting = QState(order_state)

        order_state.setInitialState(order_init)

        order_init.addTransition(self.sigConnected, order_standby )
        order_standby.addTransition(self.sigRequestOrder, order_waiting )
        order_waiting.addTransition(self.sigOrderWaitingComplete, order_standby )
        order_waiting.addTransition(self.sigOrderResponseError, order_standby )

        # state entered slot connect
        order_init.entered.connect(self.order_init_entered)
        order_standby.entered.connect(self.order_standby_entered)
        order_waiting.entered.connect(self.order_waiting_entered)

        #fsm start

        self.fsm.start()
        pass

if __name__ == "__main__":
    myApp = QApplication(sys.argv)
    handler = logging.StreamHandler()
    log.setLevel(logging.INFO)

    handler.setFormatter(logging.Formatter( '%(asctime)s [%(levelname)s] %(message)s - %(name)s:%(funcName)s:%(lineno)d' ) )
    log.addHandler( handler ) 

    common_util.process_qt_events(kw_obj.isConnected,  60)

    log.info('done')
    sys.exit(myApp.exec_())
    pass