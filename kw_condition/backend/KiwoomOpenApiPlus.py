# -*-coding: utf-8 -
from ast import Call
import sys, os, platform, re
from timeit import repeat
from typing import Callable

from PySide2.QtCore import QObject, SIGNAL, SLOT, Slot, Signal, QStateMachine, QState, QFinalState
from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QApplication
from PySide2.QtAxContainer import QAxWidget

from kw_condition.utils import common_util
from kw_condition.utils import kw_util

TR_TIME_LIMIT_MS = 250 # 연속 TR 시 딜레이로 1초 5회 제한이나 과도하게 요청시 팝업 발생해서 요청을 막음 

class KiwoomOpenApiPlus(QObject):
    sigInitOk = Signal()
    sigConnected = Signal()
    sigDisconnected = Signal()
    sigTryConnect = Signal()

    sigStateStop = Signal()

    sigRequestTR = Signal()
    sigTRWaitingComplete  = Signal()
    sigTrResponseError = Signal()

    def __init__(self):
        super().__init__()
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

        self.fsm = QStateMachine()
        assert platform.architecture()[0] == "32bit", "Control object should be created in 32bit environment"

#         self.account_list = []
#         self.timerSystem = QTimer()

        self.kospiCodeList = () 
        self.kosdaqCodeList = () 
        self.code_by_names = {}

        self.request_tr_list = [] # [ {}, {},... ]
        self.result_tr_list = {} # { rqname: data }

        self.condition_names_dict = {}

        self.create_state()
        self.create_connection()

        self.screen_numbers = {}
        self.screen_numbers['free'] = []
        self.screen_numbers['occupy'] = []
        self.screen_numbers['free'] = ['{0:0>4}'.format( number_str ) for number_str in range ( 9000, 9200) ]
        pass

        # self.currentTime = datetime.datetime.now()

#         self.marginInfo = {}
#         self.maesu_wait_list = {}
#         self.lastMaedoInfo = {}

#         # 잔고 정보 저장시 저장 제외될 키 값들 
#         self.jango_remove_keys = [ 
#             '매도호가1', '매도호가2', '매도호가3', '매도호가수량1', '매도호가수량2', '매도호가수량3','매도호가총잔량',
#             '매수호가1', '매수호가2', '매수호가3', '매수호가수량1', '매수호가수량2', '매수호가수량3', '매수호가총잔량',
#             '현재가', '호가시간', '세금', '전일종가', '현재가', '종목번호', '수익율', '수익', '잔고' , '매도중', '시가', '고가', '저가', '장구분', 
#             '거래량', '등락율', '전일대비', '기준가', '상한가', '하한가',
#             '일{}봉'.format(user_setting.MAX_SAVE_CANDLE_COUNT), '{}분{}봉'.format(user_setting.REQUEST_MINUTE_CANDLE_TYPE, user_setting.MAX_SAVE_CANDLE_COUNT)  ]

    def create_connection(self):
        self.ocx.connect( SIGNAL("OnEventConnect(int)"), self._OnEventConnect )
        self.ocx.connect( SIGNAL("OnReceiveMsg(const QString&,, const QString&, const QString&, const QString&)"), self._OnReceiveMsg )
        self.ocx.connect( SIGNAL("OnReceiveTrData(const QString&, const QString&, const QString&, const QString&, const QString&, int, const QString&, const QString&, const QString&)" ), self._OnReceiveTrData )
        self.ocx.connect( SIGNAL("OnReceiveRealData(const QString&, const QString&, const QString&)"), self._OnReceiveRealData )

        self.ocx.connect( SIGNAL( "OnReceiveChejanData(const QString&, int, const QString&)"), self._OnReceiveChejanData )
        self.ocx.connect( SIGNAL( "OnReceiveConditionVer(int, const QString&)" ), self._OnReceiveConditionVer )
        self.ocx.connect( SIGNAL( "OnReceiveTrCondition(const QString&, const QString&, const QString&, int, int)" ), self._OnReceiveTrCondition )
        self.ocx.connect( SIGNAL( "OnReceiveRealCondition(const QString&, const QString&, const QString&, const QString&)" ),  self._OnReceiveRealCondition )

        # self.timerSystem.setInterval(1000) 
        # self.timerSystem.timeout.connect(self.onTimerSystemTimeout) 
        
    def create_state(self):

        # state defintion
        main_state = QState(QState.ParallelStates, self.fsm)       
        base_state = QState(main_state)
        sub_state = QState(main_state)

        self.fsm.setInitialState(main_state)

        base_state.entered.connect(self.base_state_entered)
        sub_state.entered.connect(self.sub_state_entered)

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
        tr_init = QState(sub_state)
        tr_standby = QState(sub_state)
        tr_waiting = QState(sub_state)

        sub_state.setInitialState(tr_init)

        tr_init.addTransition(self.sigConnected, tr_standby )
        tr_standby.addTransition(self.sigRequestTR, tr_waiting )
        tr_waiting.addTransition(self.sigTRWaitingComplete, tr_standby )
        tr_waiting.addTransition(self.sigTrResponseError, tr_standby )

        # state entered slot connect
        tr_init.entered.connect(self.tr_init_entered)
        tr_standby.entered.connect(self.tr_standby_entered)
        tr_waiting.entered.connect(self.tr_waiting_entered)

        #fsm start
        self.fsm.start()
        pass


    def get_screen_number(self) -> str:
        number = self.screen_numbers['free'].pop()
        self.screen_numbers['occupy'].insert(0, number)
        return number

        return self.screen_numbers['free'].pop()

    def release_screen_number(self, number : str) -> None:
        if( number in self.screen_numbers['occupy'] ):
            self.screen_numbers['occupy'].remove( number )
            self.screen_numbers['free'].insert(0, number )
        pass

    def request_transaction(self) -> None:
        ''' 
        rqname 의 경우 unique 하여야 하며, 
        get_transaction_result 사용시 rqname 을 통해서 한다. 
        get_transaction_result 한 후 결과 값을 버퍼에서 지우도록 한다. 
        '''

        request = None
        if( len(self.request_tr_list) != 0 ):
            request = self.request_tr_list.pop(0)
        else:
            print( 'request tr list empty!' )
            return

        # print('{} {}'.format( common_util.whoami(), request) )

        for key, value in request['inputs'].items() :
            # print(key, value)
            self.setInputValue(key, value)

        ret = self.commRqData(request['rqname'], request['trcode'], request['prev_next'], request['screen_no'] )
        if( ret != 0 ):
            print( 'commRqData Err: {} {}'.format( common_util.whoami(), request )  )
        pass

    def add_transaction(self, rqname: str, trcode: str, inputs: dict, prev_next : int = 0, screen_no: str = 'empty') -> None:
        ''' 
        rqname 의 경우 unique 하여야 하며, 
        get_transaction_result 사용시 rqname 을 통해서 한다. 
        get_transaction_result 한 후 결과 값을 버퍼에서 지우도록 한다. 
        '''

        if( screen_no == 'empty'):
            screen_no = self.get_screen_number()
            pass

        self.request_tr_list.append( { 'rqname' : rqname, 'trcode' : trcode, 'screen_no' : screen_no, 'prev_next' : prev_next, 'inputs': inputs } )

        # print('{} {}'.format( common_util.whoami(), self.request_tr_list ) )
        self.sigRequestTR.emit()
        pass
    
    def has_transaction_result(self, rqname: str) -> Callable[[], bool]:
        def check_transation():
            return rqname in self.result_tr_list
        return check_transation


    def get_transaction_result(self, rqname: str) -> list:
        if( rqname in self.result_tr_list ):
            return self.result_tr_list.pop(rqname)['data']
        else:
            print(" transation result null")
            return [] 

    # 연속으로 데이터 요청할 것이 있는지 판단 
    def has_transaction_additional_data(self, rqname: str) -> bool:
        if( rqname in self.result_tr_list ):
            prev_next = self.result_tr_list[rqname].get( 'prev_next', 0 )
            return prev_next == '2'
        else:
            return False 

    def load_condition_names(self):
        self.getConditionLoad()

    def has_condition_names(self) -> bool:
        if( len(self.condition_names_dict) == 0):
            return False
        else:
            return True
    def get_condition_names(self) -> dict:
        return self.condition_names_dict
    
    def request_condition(self, condition_name: str) -> str:
        if( condition_name not in self.condition_names_dict ):
            print('condition name {} not exist'.format( condition_name) )
            pass
        else:
            self.sendCondition('0010', condition_name, self.condition_names_dict[condition_name], 0)

    @Slot(str, str, int, int)
    def sendCondition(self, scrNo, conditionName, index, search):
        self.ocx.dynamicCall("SendCondition(QString,QString, int, int)", [scrNo, conditionName, index, search])
        pass

  
    @Slot()
    def base_state_entered(self):
        # print(common_util.whoami())
        pass

    @Slot()
    def sub_state_entered(self):
        # print(common_util.whoami())
        pass

    ##########################################################


    @Slot()
    def init_entered(self):
        # print(common_util.whoami())
        self.sigInitOk.emit()
        pass

    @Slot()
    def disconnected_entered(self):
        # print(common_util.whoami())
        if( self.getConnectState() == 1 ):
            self.sigConnected.emit()
            
    @Slot()
    def connected_entered(self):
        print(common_util.whoami())
        # get 계좌 정보

        account_cnt = self.getLoginInfo("ACCOUNT_CNT")
        acc_num = self.getLoginInfo("ACCNO")
        user_id = self.getLoginInfo("USER_ID")
        user_name = self.getLoginInfo("USER_NAME")
        keyboard_boan = self.getLoginInfo("KEY_BSECGB")
        firewall = self.getLoginInfo("FIREW_SECGB")
        print("account count: {}, "
                #"acc_num: {}, user id: {}, "user_name: {}, "
                "keyboard_boan: {}, firewall: {}"
                .format(account_cnt, 
                    #acc_num, user_id, user_name, 
                    keyboard_boan, firewall))

        self.account_list = (acc_num.split(';')[:-1])

        # 코스피 , 코스닥 종목 코드 리스트 얻기 
        result = self.getCodeListByMarket('0')
        self.kospiCodeList = tuple(result.split(';'))
        result = self.getCodeListByMarket('10')
        self.kosdaqCodeList = tuple(result.split(';'))

        # for code in self.kospiCodeList:
        #     print(self.getMasterCodeName(code) )

        names = [self.getMasterCodeName(code) for code in self.kospiCodeList]
        names.extend( [self.getMasterCodeName(code) for code in self.kosdaqCodeList] )

        self.code_by_names = dict( zip( names, [*self.kospiCodeList, *self.kosdaqCodeList ] ) )
        pass

    @Slot()
    def sub_state_entered(self):
        # print(common_util.whoami() )
        pass


    @Slot()
    def tr_init_entered(self):
        # print(common_util.whoami() )
        pass

    @Slot()
    def tr_standby_entered(self):
        # print(common_util.whoami() )
        if( len(self.request_tr_list) != 0):
            self.sigRequestTR.emit()
            pass

    @Slot()
    def tr_waiting_entered(self):
        # print(common_util.whoami() )

        self.request_transaction()
        QTimer.singleShot(TR_TIME_LIMIT_MS, self.sigTRWaitingComplete)
        pass

   
    def sendorder_multi(self, rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo):
        def inner():
            self.sendOrder(rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo)
        return inner

    # 계좌평가현황요청
    @Slot(str, result = bool)
    def requestOpw00004(self, account_num ):
        self.setInputValue('계좌번호', account_num)
        self.setInputValue('비밀번호', '') #  사용안함(공백)
        self.setInputValue('상장폐지조회구분', '1')
        self.setInputValue('비밀번호입력매체구분', '00')

        ret = self.commRqData('{}_opw00004'.format(account_num), "opw00004", 0, kw_util.sendYesuGmInfoScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString =   account_num + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True
        pass

    # 계좌평가현황 정보 생성
    def makeOpw00004Info(self, rQName):
        for item_name in kw_util.dict_jusik['TR:계좌평가현황']:
            result = self.getCommData("opw00004", rQName, 0, item_name)
            print( '{}: {}'.format( item_name, result ) )

    # 체결잔고요청
    @Slot(str, result = bool)
    def requestOpw00005(self, account_num ):
        self.setInputValue('계좌번호', account_num)
        self.setInputValue('비밀번호', '') #  사용안함(공백)
        self.setInputValue('비밀번호입력매체구분', '00')

        ret = self.commRqData('{}_opw00005'.format(account_num), "opw00005", 0, kw_util.sendChegyeolJangoInfoScreenNo) 

        errorString = None
        if( ret != 0 ):
            errorString =   account_num + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True
        pass

    # 체결잔고요청정보 생성
    def makeOpw00005Info(self, rQName):
        for item_name in kw_util.dict_jusik['TR:체결잔고']:
            result = self.getCommData("opw00005", rQName, 0, item_name)
            self.marginInfo[item_name] = int(result)
            print( '{}: {}'.format( item_name, result ) )

    # 주식 잔고정보 요청 
    @Slot(str, str, result = bool)
    def requestOpw00018(self, account_num, sPrevNext):
        self.setInputValue('계좌번호', account_num)
        self.setInputValue('비밀번호', '') #  사용안함(공백)
        self.setInputValue('비빌번호입력매체구분', '00')
        self.setInputValue('조회구분', '1')

        # 연속 데이터 조회해야 하는 경우 
        ret = 0
        if( sPrevNext == "2" ):
            ret = self.commRqData(account_num, "opw00018", 2, kw_util.sendAccountInfoScreenNo) 
        else:
            ret = self.commRqData(account_num, "opw00018", 0, kw_util.sendAccountInfoScreenNo) 

        errorString = None
        if( ret != 0 ):
            errorString =   account_num + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True

    # 주식 잔고 정보 #rQName 의 경우 계좌 번호로 넘겨줌
    def makeOpw00018Info(self, rQName):
        data_cnt = self.getRepeatCnt('opw00018', rQName)
        for cnt in range(data_cnt):
            info_dict = {}
            for item_name in kw_util.dict_jusik['TR:계좌평가잔고내역요청']:
                result = self.getCommData("opw00018", rQName, cnt, item_name)
                # 없는 컬럼은 pass 
                if( len(result) == 0 ):
                    continue
                if( item_name == '종목명'):
                    info_dict[item_name] = result.strip() 
                elif( item_name == '종목번호'):
                    info_dict[item_name] = result[1:-1].strip()
                elif( item_name == '수익률(%)'):
                    info_dict[item_name] = int(result) / 100
                else: 
                    info_dict[item_name] = int(result)
        
            jongmok_code = info_dict['종목번호']
            info_dict['업종'] = self.getMasterStockInfo(jongmok_code)
            
            if( jongmok_code not in self.jangoInfo.keys() ):
                self.jangoInfo[jongmok_code] = info_dict
            else:
                # 기존에 가지고 있는 종목이면 update
                self.jangoInfo[jongmok_code].update(info_dict)

        # print(self.jangoInfo)
        return True 
   
    @Slot()
    def onTimerSystemTimeout(self):
        current_time = self.currentTime.time()
        pass

    @Slot()
    def quit(self):
        print(common_util.whoami())
        self.commTerminate()
        QApplication.quit()

    # event
    # 통신 연결 상태 변경시 이벤트
    # nErrCode가 0이면 로그인 성공, 음수면 실패
    def _OnEventConnect(self, errCode):
        print(common_util.whoami() + '{}'.format(errCode))
        if errCode == 0:
            self.sigConnected.emit()
        else:
            self.sigDisconnected.emit()

    # 수신 메시지 이벤트
    def _OnReceiveMsg(self, scrNo, rQName, trCode, msg):
        # print(common_util.whoami() + 'sScrNo: {}, sRQName: {}, sTrCode: {}, sMsg: {}'
        # .format(scrNo, rQName, trCode, msg))

        # [107066] 매수주문이 완료되었습니다.
        # [107048] 매도주문이 완료되었습니다
        # [571489] 장이 열리지않는 날입니다
        # [100000] 조회가 완료되었습니다
        printData =  'sScrNo: {}, sRQName: {}, sTrCode: {}, sMsg: {}'.format(scrNo, rQName, trCode, msg)

        # buy 하다가 오류 난경우 강제로 buy signal 생성  
        # buy 정상 메시지는 107066
        if( 'buy' in rQName and '107066' not in msg ):
            self.sigWaitTr.emit()

        # sell 하다가 오류 난경우 강제로 buy signal 생성  
        # sell 정상 메시지는 107066
        if( 'sell' in rQName and '107048' not in msg ):
            pass
            # self.sigWaitTr.emit()

        # sell 하다가 오류 난경우 
        # if( 'sell' in rQName and '매도가능수량' in msg ):
        #     self.sigWaitTr.emit()

        print(printData)
        pass

    # Tran 수신시 이벤트
    def _OnReceiveTrData(   self, scrNo, rQName, trCode, recordName, prevNext, 
                            # not used
                            dataLength, errorCode, message, splmMsg):
        print('{} sScrNo: {}, rQName: {}, trCode: {}, recordName: {}, prevNext {}'.format(common_util.whoami(), scrNo, rQName, trCode, recordName, prevNext ))


        self.release_screen_number(scrNo)

        # 단일 데이터인지 복수 데이터 인지 확인 
        # 단일 데이터인 경우 리턴값이 0 임 
        repeat_cnt = self.getRepeatCnt(trCode, rQName)

        if( repeat_cnt != 0 ):
            # 복수 데이터 처리 
            for i in range(repeat_cnt): 

                row_values = []
                for item_name in kw_util.tr_column_info[trCode]:
                    result = self.getCommData(trCode, rQName, i, item_name)
                    row_values.append( result.strip() )

                if(rQName not in  self.result_tr_list):
                    self.result_tr_list[rQName] = {}
                    self.result_tr_list[rQName]['prev_next'] = 0
                    self.result_tr_list[rQName]['data'] = [] 

                self.result_tr_list[rQName]['data'].append( row_values )
                self.result_tr_list[rQName]['prev_next'] = prevNext

                # print( '{}: {}'.format(item_name, result ) )
            pass
        else:
            #단일 데이터 처리 
            row_values = []
            for item_name in kw_util.tr_column_info[trCode]:
                result = self.getCommData(trCode, rQName, 0, item_name)
                row_values.append(result.strip() )

            self.result_tr_list[rQName] = {} 
            self.result_tr_list[rQName]['data'] = row_values
            self.result_tr_list[rQName]['prev_next'] = prevNext
            # print( '{}: {}'.format(item_name, result ) )
            pass

        return True

        if ( trCode == 'opw00018' ):
        # 게좌 정보 요청 rQName 은 계좌번호임 
            if( self.makeOpw00018Info(rQName) ):
                # 연속 데이터 존재 하는 경우 재 조회 
                if( prevNext  == "2" ) :
                    QTimer.singleShot(20, lambda: self.requestOpw00018(self.account_list[0], prevNext) )
                else:
                    QTimer.singleShot(TR_TIME_LIMIT_MS,  self.sigRequestJangoComplete)

            else:
                self.sigError.emit()
            pass

    # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmok_code, realType, realData):
        # print('{} jongmok_code: {}, {}, realType: {}'.format(common_util.whoami(), jongmok_code, self.getMasterCodeName(jongmok_code),  realType))
        pass

        # # 장전에도 주식 호가 잔량 값이 올수 있으므로 유의해야함 
        # if( realType == "주식호가잔량"):
        #     # print(util.whoami() + 'jongmok_code: {}, realType: {}, realData: {}'
        #     #     .format(jongmok_code, realType, realData))

        #     self.makeRealDataInfo(jongmok_code, '실시간-{}'.format(realType) ) 

        # elif( realType == "주식체결"):
        #     # WARNING: 거래량이 많아서 주식 체결 데이터가 너무 많아 지는 경우 주의 
        #     # print(util.whoami() + 'jongmok_code: {}, realType: {}, realData: {}'
        #     #     .format(jongmok_code, realType, realData))
        #     self.makeRealDataInfo(jongmok_code, '실시간-{}'.format(realType) ) 
        #     pass

        # elif( realType == "업종지수" ):
        #     # print(util.whoami() + 'jongmok_code: {}, realType: {}, realData: {}'
        #     #     .format(jongmok_code, realType, realData))
        #     result = '' 
        #     key_name = ''
        #     if( jongmok_code == '001'):
        #         key_name = '코스피'
        #     elif( jongmok_code == '101'):
        #         key_name = '코스닥'
        #     upjong = self.upjongInfo[key_name]

        #     for col_name in kw_util.dict_jusik['실시간-{}'.format(realType)]:
        #         result = self.getCommRealData(jongmok_code, kw_util.name_fid[col_name] ) 
        #         upjong[col_name] = result.strip()

        #     if( '분봉' in upjong ):
        #         # 분봉 정보는 소수점이 없고 실시간 정보는 소수점 둘째자리 표시되는 문자열임
        #         current_price_str = str(round(float(upjong['현재가']) * 100, 2) )
        #         current_chegyeol_time_str = upjong['체결시간']
        #         # 장마감후 '체결시간' 이 장마감 문자열로 옴
        #         if( current_chegyeol_time_str != '장마감'):
        #             current_chegyeol_time = datetime.datetime.strptime(current_chegyeol_time_str, "%H%M%S").time().replace(second=0)
        #         else:
        #             current_chegyeol_time = self.currentTime.time()

        #         last_chegyeol_time_str = upjong['분봉'][0].split(':')[1]
        #         last_chegyeol_time = datetime.datetime.strptime(last_chegyeol_time_str, "%Y%m%d%H%M%S")

        #         time_span = datetime.timedelta(minutes= 3)

        #         if( current_chegyeol_time >= (last_chegyeol_time + time_span).time().replace(second=0) ):
        #             upjong['분봉'].insert(0, '{}:{}'.format(current_price_str, '19990101{}'.format( current_chegyeol_time_str) ) )
        #             upjong['분봉'] = upjong['분봉'][0:40]
        #             # print(self.upjongInfo[key_name])
        
        # elif( realType == '장시작시간'):
        #     # TODO: 장시작 30분전부터 실시간 정보가 올라오는데 이를 토대로 가변적으로 장시작시간을 가늠할수 있도록 기능 추가 필요 
        #     # 장운영구분(0:장시작전, 2:장종료전, 3:장시작, 4,8:장종료, 9:장마감)
        #     # 동시호가 시간에 매수 주문 
        #     result = self.getCommRealData(realType, kw_util.name_fid['장운영구분'] ) 
        #     if( result == '2'):
        #         self.sigTerminating.emit()
        #     elif( result == '4' ): # 장종료 후 5분뒤에 프로그램 종료 하게 함  
        #         QTimer.singleShot(300000, self.sigStockComplete)

        #     print(util.whoami() + 'jongmok_code: {}, realType: {}, realData: {}'
        #         .format(jongmok_code, realType, realData))
        #     pass
        # elif( realType == "주식당일거래원"): 
        #     jongmok_name = self.getMasterCodeName(jongmok_code)
        #     line_str = [] 
        #     for col_name in kw_util.dict_jusik['실시간-{}'.format(realType)]:
        #         result = self.getCommRealData(jongmok_code, kw_util.name_fid[col_name] ) 
        #         line_str.append( '{}'.format( result ) )

        #     pass

        # elif( realType == '주식우선호가' or realType == '업종등락' or realType =='주식예상체결' ):
        #     pass

        # else:
        #     # 주식시세는 장종료 후에 나옴 
        #     pass


    # 체결데이터를 받은 시점을 알려준다.
    # sGubun – 0:주문체결통보, 1:잔고통보, 3:특이신호
    # sFidList – 데이터 구분은 ‘;’ 이다.
    '''
    매수시 
    14:03:36.218242 _OnReceiveChejanData gubun: 0, itemCnt: 35, fidList: 9201;9203;9205;9001;912;913;302;900;901;902;903;904;905;906;907;908;909;910;911;10;27;28;914;915;938;939;919;920;921;922;923;949;10010;969;819
    * 14:03:36.250244 _OnReceiveChejanData gubun: 0, itemCnt: 35, fidList: 9201;9203;9205;9001;912;913;302;900;901;902;903;904;905;906;907;908;909;910;911;10;27;28;914;915;938;939;919;920;921;922;923;949;10010;969;819
    * 14:03:36.353244 _OnReceiveChejanData gubun: 1, itemCnt: 34, fidList: 9201;9001;917;916;302;10;930;931;932;933;945;946;950;951;27;28;307;8019;957;958;918;990;991;992;993;959;924;10010;25;11;12;306;305;970
    '''
    '''
    _OnReceiveChejanData gubun: 1, itemCnt: 27, fidList: 9201;9001;917;916;302;10;930;931;932;933;945;946;950;951;27;28;307;8019;957;958;918;990;991;992;993;959;924
    {'종목코드': 'A010050', '당일실현손익률(유가)': '0.00', '대출일': '00000000', '당일실현손익률(신용)': '0.00', '(최우선)매수호가': '+805', '당일순매수수량': '5', '총매입가': '4043', 
    '당일총매도손일': '0', '만기일': '00000000', '신용금액': '0', '당일실현손익(신용)': '0', '현재가': '+806', '기준가': '802', '계좌번호': ', '보유수량': '5', 
    '예수금': '0', '주문가능수량': '5', '종목명': '우리종금                                ', '손익율': '0.00', '당일실현손익(유가)': '0', '담보대출수량': '0', '924': '0', 
    '매입단가': '809', '신용구분': '00', '매도/매수구분': '2', '(최우선)매도호가': '+806', '신용이자': '0'}
    ''' 
    # receiveChejanData 에서 말씀하신 951번 예수금데이터는 제공되지 않습니다. from 운영자
    def _OnReceiveChejanData(self, gubun, itemCnt, fidList):
        # print(util.whoami() + 'gubun: {}, itemCnt: {}, fidList: {}'
        #         .format(gubun, itemCnt, fidList))
        if( gubun == "1"): # 잔고 정보
            # 잔고 정보에서는 매도/매수 구분이 되지 않음 

            jongmok_code = self.getChejanData(kw_util.name_fid['종목코드'])[1:]
            boyou_suryang = int(self.getChejanData(kw_util.name_fid['보유수량']))
            jumun_ganeung_suryang = int(self.getChejanData(kw_util.name_fid['주문가능수량']))
            maeip_danga = int(self.getChejanData(kw_util.name_fid['매입단가']))
            jongmok_name= self.getMasterCodeName(jongmok_code)
            current_price = abs(int(self.getChejanData(kw_util.name_fid['현재가'])))
            current_amount = abs(int(self.getChejanData(kw_util.name_fid['당일순매수수량'])))
            maesuHoga1 = abs(int(self.getChejanData(kw_util.name_fid['(최우선)매수호가'])))
            maedoHoga1 = abs(int(self.getChejanData(kw_util.name_fid['(최우선)매도호가'])))
            maemae_type = int( self.getChejanData(kw_util.name_fid['매도/매수구분']) )

            # 아래 잔고 정보의 경우 TR:계좌평가잔고내역요청 필드와 일치하게 만들어야 함 
            current_jango = {}
            current_jango['보유수량'] = boyou_suryang
            current_jango['매매가능수량'] =  jumun_ganeung_suryang # TR 잔고에서 매매가능 수량 이란 이름으로 사용되므로 
            current_jango['매입가'] = maeip_danga
            current_jango['종목번호'] = jongmok_code
            current_jango['종목명'] = jongmok_name.strip()
            current_jango['업종'] = self.getMasterStockInfo(jongmok_code)
 
            printData = ''
            if( maemae_type == 1 ):
                printData = "{}: 매도 주문가능수량:{} / 보유수량:{}".format( jongmok_name, jumun_ganeung_suryang, boyou_suryang)
            else:
                printData = "{}: 매수 주문가능수량:{} / 보유수량:{}".format( jongmok_name, jumun_ganeung_suryang, boyou_suryang)

            util.save_log(printData, "*잔고정보", folder= "log")

            # 매수  
            if( maemae_type == 2 ):
                chegyeol_info = util.cur_date_time('%Y%m%d%H%M%S') + ":" + str(maeip_danga) + ":" + str(current_amount)
                if( jongmok_code not in self.jangoInfo):
                    # 첫매수
                    current_jango['분할매수이력'] = [chegyeol_info] 
                    self.jangoInfo[jongmok_code] = current_jango 
                else:
                    # 분할매수
                    last_chegyeol_info = self.jangoInfo[jongmok_code]['분할매수이력'][-1]
                    last_price = int(last_chegyeol_info.split(':')[1])
                    if( last_price != current_price ):
                        chegyeol_info_list = self.jangoInfo[jongmok_code].get('분할매수이력', [])
                        chegyeol_info_list.append( chegyeol_info )
                        current_jango['분할매수이력'] = chegyeol_info_list
                    pass

                self.removeProhibitList( jongmok_code )
            # 매도
            else:
                if( boyou_suryang == 0 ):
                    # 보유 수량이 0 인 경우 완전 매도 수행한 것임  
                    self.sigRemoveJongmokInfo.emit(jongmok_code)
                else:
                    # 분할매도
                    current_amount = boyou_suryang - jumun_ganeung_suryang
                    chegyeol_info = util.cur_date_time('%Y%m%d%H%M%S') + ":" + str(current_price) + ":" + str(current_amount)

                    chegyeol_info_list = self.jangoInfo[jongmok_code].get('분할매도이력', [])  
                    chegyeol_info_list.append( chegyeol_info )
                    current_jango['분할매도이력'] = chegyeol_info_list
                    pass

                    if( '매도중' in self.jangoInfo[jongmok_code] ):
                        del self.jangoInfo[jongmok_code]['매도중']

            # 매도로 다 팔아 버린 경우가 아니라면 
            if( jongmok_code in self.jangoInfo ):
                self.jangoInfo[jongmok_code].update(current_jango)
            self.makeJangoInfoFile()
            pass

        elif ( gubun == "0"):
            # 접수 또는 체결 
            jumun_sangtae =  self.getChejanData(kw_util.name_fid['주문상태'])
            jongmok_code = self.getChejanData(kw_util.name_fid['종목코드'])[1:]
            jongmok_name= self.getMasterCodeName(jongmok_code)
            jumun_chegyeol_time = self.getChejanData( kw_util.name_fid['주문/체결시간'] )
            michegyeol_suryang = int(self.getChejanData(kw_util.name_fid['미체결수량']))
            maemae_type = int( self.getChejanData(kw_util.name_fid['매도매수구분']) )
            jumun_qty = int(self.getChejanData(kw_util.name_fid['주문수량']))
            jumun_price = int(self.getChejanData(kw_util.name_fid['주문가격']))


            # 주문 상태 
            # 매수 시 접수(gubun-0) - 체결(gubun-0) - 잔고(gubun-1)  바로 처리 되지 않는 경우?   접수 - 체결 - 잔고 - 체결 - 잔고 - 체결 - 잔고 
            # 매도 시 접수(gubun-0) - 잔고(gubun-1) - 체결(gubun-0) - 잔고(gubun-1)   순임 


            if( jumun_sangtae == "체결"):
                # 매수 체결과 매도 체결 구분해야함 

                # 미체결 수량이 0 이 아닌 경우 다시 체결 정보가 올라 오므로 0인경우만 처리하도록 함 
                if( michegyeol_suryang == 0 ):
                    self.makeChegyeolInfo(jongmok_code, fidList)
                    self.makeChegyeolInfoFile()

                    # 체결정보의 경우 체결 조금씩 될때마다 수행되므로 이를 감안 해야함
                    self.timerD2YesugmRequest.start()
                    self.timerRealInfoRefresh.start()

                    # 매수주문 번호를 초기화 해서 즉시 매도 조건 걸리게 함 
                    if( jongmok_code in self.maesu_wait_list ):
                        del self.maesu_wait_list[jongmok_code]

                    if( maemae_type == 1 ):
                        # 매도인 경우 
                        self.lastMaedoInfo[jongmok_code] = {}
                        self.lastMaedoInfo[jongmok_code]["time"] = jumun_chegyeol_time
                        self.lastMaedoInfo[jongmok_code]["price"] =  str(jumun_price)
                        self.lastMaedoInfo[jongmok_code]["qty"] =  str(jumun_qty)

                printData = ''
                if( maemae_type == 1 ):
                    printData = "{}: 매도 {} 미체결수량 {}".format( jongmok_name, jumun_sangtae, michegyeol_suryang)
                else:
                    printData = "{}: 매수 {} 미체결수량 {}".format( jongmok_name, jumun_sangtae, michegyeol_suryang)

                util.save_log(printData, "*체결정보", folder= "log")

                pass
            elif ( jumun_sangtae == '접수'):
                jumun_number = self.getChejanData(kw_util.name_fid['주문번호'])
                # 매도 접수인 경우
                printData = '' 
                if( jongmok_code in self.jangoInfo ):
                    prinData = "sell: {} ordernumber: {}, 접수시간 {}, 가격 {}, 수량 {}".format( jongmok_name, jumun_number, jumun_chegyeol_time, jumun_price, jumun_qty ) 
                    self.jangoInfo[jongmok_code]['매도주문번호'] = jumun_number
                else:
                    if( jongmok_code not in self.maesu_wait_list ):
                        printData = "buy: {} ordernumber: {}, 접수시간 {}, 가격 {}, 수량 {}".format( jongmok_name, jumun_number, jumun_chegyeol_time, jumun_price, jumun_qty ) 
                        self.maesu_wait_list[jongmok_code] = {}
                        self.maesu_wait_list[jongmok_code]['매수주문번호'] = jumun_number
                        self.maesu_wait_list[jongmok_code]['매수접수시간'] = jumun_chegyeol_time
                        self.maesu_wait_list[jongmok_code]['주문수량'] = jumun_qty
                    else:
                        # 매수 취소도 이쪽으로 옴 
                        # 매수 취소 시 아래와 같이 2개의 요청이 옴 
                        # 매수 취소 요청 접수: order buy: 켐온 ordernumber: 0040221, 매수 접수 시간 111243, 수량 44
                        # 기존 매수 취소 접수: order buy: 켐온 ordernumber: 0039559, 매수 접수 시간 110742, 수량 44
                        if( self.maesu_wait_list[jongmok_code]['매수주문번호'] == jumun_number):
                            printData = "cancel buy: {} ordernumber: {}, 접수시간 {}, 가격 {}, 수량 {}".format( jongmok_name, jumun_number, jumun_chegyeol_time, jumun_price, jumun_qty ) 
                            del self.maesu_wait_list[jongmok_code]
                        else:
                            printData = "cancel request buy: {} ordernumber: {}, 접수시간 {}, 가격 {}, 수량 {}".format( jongmok_name, jumun_number, jumun_chegyeol_time, jumun_price, jumun_qty ) 

                util.save_log(printData, "*접수정보", folder= "log")


            elif ( jumun_sangtae == '취소' or jumun_sangtae == '거부'):
                # 매수주문 번호를 초기화 해서 즉시 매도 조건 걸리게 함 
                if( jongmok_code in self.maesu_wait_list ):
                    del self.maesu_wait_list[jongmok_code]
                pass
            else:
                printData = "{}, {}".format( jongmok_name, jumun_sangtae)
                util.save_log(printData, "*접수정보", folder= "log")
                # 기타 상태인 경우 취소, 확인?
                pass
            pass


    # 로컬에 사용자조건식 저장 성공여부 응답 이벤트
    # 0:(실패) 1:(성공)
    def _OnReceiveConditionVer(self, ret, msg):
        print('{} ret: {}, msg: {}'.format(common_util.whoami(), ret, msg))
        if ret == 1:
            # 반환값 : 조건인덱스1^조건명1;조건인덱스2^조건명2;…;
            # result = '조건인덱스1^조건명1;조건인덱스2^조건명2;'
            result = self.getConditionNameList()
            searchPattern = r'(?P<index>[^\/:*?"<>|;]+)\^(?P<name>[^\/:*?"<>|;]+);'
            fileSearchObj = re.compile(searchPattern, re.IGNORECASE)
            findList = fileSearchObj.findall(result)

            for item in findList:
                # 종목이름: index
                self.condition_names_dict[item[1]] = int(item[0])
            


    # 조건검색 조회응답으로 종목리스트를 구분자(“”)로 붙어서 받는 시점.
    # LPCTSTR sScrNo : 종목코드
    # LPCTSTR strCodeList : 종목리스트(“;”로 구분)
    # LPCTSTR strConditionName : 조건명
    # int nIndex : 조건명 인덱스
    # int nNext : 연속조회(2:연속조회, 0:연속조회없음)
    def _OnReceiveTrCondition(self, scrNo, codeList, conditionName, index, next):
        print('{} scrNo: {}, codeList: {}, conditionName: {} index: {}, next: {}'.format(common_util.whoami(), scrNo, codeList, conditionName, index, next ))
        codes = codeList.split(';')[:-1]
        # 마지막 split 결과 None 이므로 삭제 

        for code in codes:
            print('condition list add: {} '.format(code) + self.getMasterCodeName(code))

            # 주의: 여기에 실시간조건 refresh 를 넣지않는다 동작오류남
            # self.refreshRealRequest()


    # 편입, 이탈 종목이 실시간으로 들어옵니다.
    # strCode : 종목코드
    # strType : 편입(“I”), 이탈(“D”)
    # streonditionName : 조건명
    # strConditionIndex : 조건명 인덱스
    def _OnReceiveRealCondition(self, code, type, conditionName, conditionIndex):

        if ( '이탈' in conditionName ):
            # print('{} {}, code: {}, 종목이름: {},  type: {},  conditionIndex: {}'
            #     .format(util.cur_time_msec(), conditionName, code, self.getMasterCodeName(code), type, conditionIndex ))
            key_name = '3분'
            if( '이탈1'  == conditionName ):
                key_name = '1분'
                pass
            elif( '이탈3' == conditionName ):
                key_name = '3분'
                pass
            elif( '이탈15' == conditionName ):
                key_name = '15분'
                pass
            elif( '이탈30' == conditionName ):
                key_name = '30분'
                pass

            if ( type == 'I' ):
                if( code not in self.conditionStoplossList[key_name]):
                    self.conditionStoplossList[key_name].append(code)
            else:
                if( code in self.conditionStoplossList[key_name]):
                    self.conditionStoplossList[key_name].remove(code)
                pass

        else:
            if ( type == 'I' ):
                print('+{} {}[{}] {}'
                    .format(util.cur_time_msec(), self.getMasterCodeName(code) , code , self.GetMasterStockState(code) ) )
                self.addConditionOccurList(code) # 조건 발생한 경우 해당 내용 list 에 추가  
            else:
                print('-{} {}[{}] {}'
                    .format(util.cur_time_msec(), self.getMasterCodeName(code) , code, self.GetMasterStockState(code) ) )

                # qt  message queue 에서 처리되게하여 data inconsistency 방지 
                QTimer.singleShot(10, lambda: self.removeConditionOccurList(code) )
                pass
            
            # 조건 반복 발생으로인한 overhead 를 줄이기 위함
            self.timerRealInfoRefresh.start()

    # method 
    # 수동 로그인설정인 경우 로그인창을 출력.
    # 자동로그인 설정인 경우 로그인창에서 자동으로 로그인을 시도합니다.
    @Slot(result=int)
    def commConnect(self):
        return self.ocx.dynamicCall("CommConnect()")

    # 서버와 현재 접속 상태를 알려줍니다.
    # 리턴값 1:연결, 0:연결안됨
    @Slot(result=int)
    def getConnectState(self):
        return self.ocx.dynamicCall("GetConnectState()")

    # 프로그램 종료없이 서버와의 접속만 단절시키는 함수입니다.
    # 함수 사용 후 사용자의 오해소지가 생기는 이유로 더 이상 사용할 수 없는 함수입니다
    @Slot()
    def commTerminate(self):
        self.ocx.dynamicCall("CommTerminate()")

    # 로그인 후 사용할 수 있으며 인자값에 대응하는 정보를 얻을 수 있습니다.
    #      
    # 인자는 다음값을 사용할 수 있습니다.
    #   
    # "ACCOUNT_CNT" : 보유계좌 갯수를 반환합니다.
    # "ACCLIST" 또는 "ACCNO" : 구분자 ';'로 연결된 보유계좌 목록을 반환합니다.
    # "USER_ID" : 사용자 ID를 반환합니다.
    # "USER_NAME" : 사용자 이름을 반환합니다.
    # "GetServerGubun" : 접속서버 구분을 반환합니다.(1 : 모의투자, 나머지 : 실거래서버)
    # "KEY_BSECGB" : 키보드 보안 해지여부를 반환합니다.(0 : 정상, 1 : 해지)
    # "FIREW_SECGB" : 방화벽 설정여부를 반환합니다.(0 : 미설정, 1 : 설정, 2 : 해지)
    @Slot(str, result=str)
    def getLoginInfo(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", [tag])

    # Tran 입력 값을 서버통신 전에 입력값일 저장한다.
    @Slot(str, str)
    def setInputValue(self, id, value):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", [id, value] )

    @Slot(str, str, int, str, result=int)
    def commRqData(self, rQName :str, trCode :str , prevNext :int, screenNo: str) -> int:
        '''
        [CommRqData() 함수]
        
        CommRqData(
        BSTR sRQName,    // 사용자 구분명 (임의로 지정, 한글지원)
        BSTR sTrCode,    // 조회하려는 TR이름
        long nPrevNext,  // 연속조회여부
        BSTR sScreenNo  // 화면번호 (4자리 숫자 임의로 지정)
        )
        
        조회요청 함수입니다.
        리턴값 0이면 조회요청 정상 나머지는 에러
        
        예)
        -200 시세과부하
        -201 조회전문작성 에러
        '''
        return self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", [rQName, trCode, prevNext, screenNo])

    # 수신 받은 데이터의 반복 개수를 반환한다.
    @Slot(str, str, result=int)
    def getRepeatCnt(self, trCode, recordName):
        return self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", [trCode, recordName])

    @Slot(str, str, str, int, str, result=str)
    def commGetData(self, jongmok_code, realType, fieldName, index, innerFieldName):
        '''
        일부 TR에서 사용상 제약이 있음므로 이 함수 대신 GetCommData()함수를 사용하시기 바랍니다.
        '''
        return self.ocx.dynamicCall("CommGetData(QString, QString, QString, int, QString)", [jongmok_code, realType, fieldName, index, innerFieldName] ).strip()

    # strRealType – 실시간 구분
    # nFid – 실시간 아이템
    # Ex) 현재가출력 - openApi.GetCommRealData(“주식시세”, 10);
    # 참고)실시간 현재가는 주식시세, 주식체결 등 다른 실시간타입(RealType)으로도 수신가능
    @Slot(str, int, result=str)
    def getCommRealData(self, realType, fid):
        return self.ocx.dynamicCall("GetCommRealData(QString, int)", [realType, fid]).strip()

    # 주식 주문을 서버로 전송한다.
    # sRQName - 사용자 구분 요청 명
    # sScreenNo - 화면번호[4]
    # sAccNo - 계좌번호[10]
    # nOrderType - 주문유형 (1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정)
    # sCode, - 주식종목코드
    # nQty – 주문수량
    # nPrice – 주문단가
    # sHogaGb - 거래구분
    # sHogaGb – 00:지정가, 03:시장가, 05:조건부지정가, 06:최유리지정가, 07:최우선지정가, 10:지정가IOC, 13:시장가IOC, 16:최유리IOC, 20:지정가FOK, 23:시장가FOK, 26:최유리FOK, 61:장전시간외종가, 62:시간외단일가, 81:장후시간외종가
    # ※ 시장가, 최유리지정가, 최우선지정가, 시장가IOC, 최유리IOC, 시장가FOK, 최유리FOK, 장전시간외, 장후시간외 주문시 주문가격을 입력하지 않습니다.
    # ex)
    # 지정가 매수 - openApi.SendOrder(“RQ_1”, “0101”, “5015123410”, 1, “000660”, 10, 48500, “00”, “”);
    # 시장가 매수 - openApi.SendOrder(“RQ_1”, “0101”, “5015123410”, 1, “000660”, 10, 0, “03”, “”);
    # 매수 정정 - openApi.SendOrder(“RQ_1”,“0101”, “5015123410”, 5, “000660”, 10, 49500, “00”, “1”);
    # 매수 취소 - openApi.SendOrder(“RQ_1”, “0101”, “5015123410”, 3, “000660”, 10, “00”, “2”);
    # sOrgOrderNo – 원주문번호
    @Slot(str, str, str, int, str, int, int, str, str, result=int)
    def sendOrder(self, rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo):
        return self.ocx.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)", [rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo])

    # 체결잔고 데이터를 반환한다.
    @Slot(int, result=str)
    def getChejanData(self, fid):
        return self.ocx.dynamicCall("GetChejanData(int)", [fid] )

    # 서버에 저장된 사용자 조건식을 가져온다.
    @Slot(result=int)
    def getConditionLoad(self):
        return self.ocx.dynamicCall("GetConditionLoad()")

    # 조건검색 조건명 리스트를 받아온다.
    # 조건명 리스트(인덱스^조건명)
    # 조건명 리스트를 구분(“;”)하여 받아온다
    @Slot(result=str)
    def getConditionNameList(self):
        return self.ocx.dynamicCall("GetConditionNameList()")

    # 조건검색 종목조회TR송신한다.
    # LPCTSTR strScrNo : 화면번호
    # LPCTSTR strConditionName : 조건명
    # int nIndex : 조건명인덱스
    # int nSearch : 조회구분(0:일반조회, 1:실시간조회, 2:연속조회)
    # 1:실시간조회의 화면 개수의 최대는 10개
    @Slot(str, str, int, int)
    def sendCondition(self, scrNo, conditionName, index, search):
        self.ocx.dynamicCall("SendCondition(QString,QString, int, int)", [scrNo, conditionName, index, search] )

    # 실시간 조건검색을 중지합니다.
    # ※ 화면당 실시간 조건검색은 최대 10개로 제한되어 있어서 더 이상 실시간 조건검색을 원하지 않는 조건은 중지해야만 카운트 되지 않습니다.
    @Slot(str, str, int)
    def sendConditionStop(self, scrNo, conditionName, index):
        self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", [scrNo, conditionName, index] )

    # 복수종목조회 Tran을 서버로 송신한다.
    # OP_ERR_RQ_STRING – 요청 전문 작성 실패
    # OP_ERR_NONE - 정상처리
    #
    # sArrCode – 종목간 구분은 ‘;’이다.
    # nTypeFlag – 0:주식관심종목정보, 3:선물옵션관심종목정보
    @Slot(str, bool, int, int, str, str)
    def commKwRqData(self, arrCode, next, codeCount, typeFlag, rQName, screenNo):
    	self.ocx.dynamicCall("CommKwRqData(QString, QBoolean, int, int, QString, QString)", [ arrCode, next, codeCount, typeFlag, rQName, screenNo ] )

    # 실시간 등록을 한다.
    # strScreenNo : 화면번호
    # strCodeList : 종목코드리스트(ex: 039490;005930;…)
    # strFidList : FID번호(ex:9001;10;13;…)
    # 	9001 – 종목코드
    # 	10 - 현재가
    # 	13 - 누적거래량
    # strOptType : 타입(“0”, “1”)
    # 타입 “0”은 항상 마지막에 등록한 종목들만 실시간등록이 됩니다.
    # 타입 “1”은 이전에 실시간 등록한 종목들과 함께 실시간을 받고 싶은 종목을 추가로 등록할 때 사용합니다.
    # ※ 종목, FID는 각각 한번에 실시간 등록 할 수 있는 개수는 100개 입니다.
    @Slot(str, str, str, str,  result=int)
    def setRealReg(self, screenNo, codeList, fidList, optType):
        return self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", [ screenNo, codeList, fidList, optType ])

    # 종목별 실시간 해제
    # strScrNo : 화면번호
    # strDelCode : 실시간 해제할 종목코드
    # -화면별 실시간해제
    # 여러 화면번호로 걸린 실시간을 해제하려면 파라메터의 화면번호와 종목코드에 “ALL”로 입력하여 호출하시면 됩니다.
    # SetRealRemove(“ALL”, “ALL”);
    # 개별화면별로 실시간 해제 하시려면 파라메터에서 화면번호는 실시간해제할
    # 화면번호와 종목코드에는 “ALL”로 해주시면 됩니다.
    # SetRealRemove(“0001”, “ALL”);
    # -화면의 종목별 실시간해제
    # 화면의 종목별로 실시간 해제하려면 파라메터에 해당화면번호와 해제할
    # 종목코드를 입력하시면 됩니다.
    # SetRealRemove(“0001”, “039490”);
    # 문서와는 달리 return 없음 
    # SetRealReg 로 등록한 함수만 해제 가능 
    @Slot(str, str)
    def setRealRemove(self, scrNo, delCode):
        self.ocx.dynamicCall("SetRealRemove(QString, QString)", [ scrNo, delCode ] )
        
        
    # 수신 데이터를 반환한다. 
    # LPCTSTR strTrCode : 조회한TR코드
    # LPCTSTR strRecordName: 조회한 TR명
    # nIndex : 복수 데이터 인덱스
    # strItemName: 아이템 명
    # 반환값: 수신 데이터
    
    @Slot(str, str, int, str, result=str)
    def getCommData(self, trCode, recordName, index, itemName):
        return self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", [trCode, recordName, index, itemName] )

    # 차트 조회한 데이터 전부를 배열로 받아온다.
    # LPCTSTR strTrCode : 조회한TR코드
    # LPCTSTR strRecordName: 조회한 TR명
    # ※항목의 위치는 KOA Studio의 TR목록 순서로 데이터를 가져옵니다.
    # 예로 OPT10080을 살펴보면 OUTPUT의 멀티데이터의 항목처럼 현재가, 거래량, 체결시간등 순으로 항목의 위치가 0부터 1씩증가합니다.
    @Slot(str, str, result=str)
    def getCommDataEx(self, trCode, recordName):
        return self.ocx.dynamicCall("GetCommDataEx(QString, QString)", [trCode, recordName] )

    # 리얼 시세를 끊는다.
    # 화면 내 모든 리얼데이터 요청을 제거한다.
    # 화면을 종료할 때 반드시 위 함수를 호출해야 한다.
    # Ex) openApi.DisconnectRealData(“0101”);
    @Slot(str)
    def disconnectRealData(self, scnNo):
        self.ocx.dynamicCall("DisconnectRealData(QString)", [scnNo] )


    def tryConnect(self):
        print( common_util.whoami() )
        self.commConnect()
        pass

    def tryDisconnect(self):
        print( common_util.whoami() )
        self.commTerminate()
        pass

    def isConnected(self) -> bool:
        # print( common_util.whoami() )
        if( self.getConnectState() != 1 ):
            return False
        else:
            return True



    # pyside2 에서 인자가 있는 dynamicCall 사용시 인자를 list 형태로 제공해야함 
    @Slot(str, result=str)
    def getCodeListByMarket(self, sMarket):
        '''
        주식 시장별 종목코드 리스트를 ';'로 구분해서 전달합니다. 
        시장구분값을 ""공백으로하면 전체시장 코드리스트를 전달합니다.
        
        로그인 한 후에 사용할 수 있는 함수입니다.
        
        [시장구분값]
        0 : 코스피
        10 : 코스닥
        3 : ELW
        8 : ETF
        50 : KONEX
        4 :  뮤추얼펀드
        5 : 신주인수권
        6 : 리츠
        9 : 하이얼펀드
        30 : K-OTC
        '''
        return self.ocx.dynamicCall("GetCodeListByMarket(QString)", [sMarket])

    @Slot(str, result=str)
    def getMasterCodeName(self, strCode: str) -> str:
        '''
        종목코드에 해당하는 종목명을 전달합니다.
        로그인 한 후에 사용할 수 있는 함수입니다.

        strCode – 종목코드
        없는 코드 일경우 empty 를 리턴함
        '''
        return self.ocx.dynamicCall("GetMasterCodeName(QString)", [strCode])

    @Slot(str, result=int)
    def getMasterListedStockCnt(self, strCode):
        '''
        입력한 종목코드에 해당하는 종목 상장주식수를 전달합니다.
        로그인 한 후에 사용할 수 있는 함수입니다.
        strCode – 종목코드

        상장주식수를 구하는 GetMasterListedStockCnt 기존 함수 사용시 특정 종목 데이터가 long형을 Overflow 하는 현상이 있습니다.
        이에, 상장주식수를 구하는 기능을 신규 추가 합니다. 사용법은 아래와 같습니다.
        
        KOA_Functions("GetMasterListedStockCntEx", "종목코드(6자리)")

        '''
        return self.ocx.dynamicCall("KOA_Functions(QString, QString)", "GetMasterListedStockCntEx", [strCode])

    @Slot(str, result=str)
    def getMasterConstruction(self, strCode):
        '''
        입력한 종목코드에 해당하는 종목의 감리구분을 전달합니다.
        (정상, 투자주의, 투자경고, 투자위험, 투자주의환기종목)
        로그인 한 후에 사용할 수 있는 함수입니다.
        strCode – 종목코드
        '''
        return self.ocx.dynamicCall("GetMasterConstruction(QString)", [strCode])

    @Slot(str, result=str)
    def getMasterListedStockDate(self, strCode):
        '''
        입력한 종목의 상장일을 전달합니다.
        로그인 한 후에 사용할 수 있는 함수입니다.
        strCode – 종목코드
        '''
        return self.ocx.dynamicCall("GetMasterListedStockDate(QString)", [strCode])

    @Slot(str, result=str)
    def getMasterLastPrice(self, strCode):
        '''
        설명 종목코드의 전일가를 반환한다. 
        입력값: strCode – 종목코드 
        반환값: 전일가  
        '''
        return self.ocx.dynamicCall("GetMasterLastPrice(QString)", [strCode])

    @Slot(str, result=str)
    def getMasterStockState(self, strCode):
        '''
        설명   입력한 종목의 증거금 비율, 거래정지, 관리종목, 감리종목, 투자융의종목, 담보대출, 액면분할, 신용가능 여부를 전달합니다.
        입력값: strCode – 종목코드 
        반환값: 종목 상태 | 구분자   
        '''
        return self.ocx.dynamicCall("GetMasterStockState(QString)", [strCode])

    @Slot(str, result=str)
    def getMasterStockInfo(self, strCode):
        '''
        주식종목 시장구분, 종목분류등 정보제공 
        strCode – 종목코드
        입력한 종목에 대한 대분류, 중분류, 업종구분값을 구분자로 연결한 문자열을 얻을수 있습니다.(여기서 구분자는 '|'와 ';'입니다.) 
        KOA_Functions("GetMasterStockInfo", 종목코드) 
        시장구분0|코스닥|벤처기업;시장구분1|소형주;업종구분|제조|기계/장비
        시장구분0|거래소;시장구분1|중형주;업종구분|서비스업;
        '''
        stock_info = self.ocx.dynamicCall("KOA_Functions(QString, QString)", "GetMasterStockInfo", [strCode])
        # api return 버그로 추가 해줌 
        kospi_kosdaq = ''
        yupjong = ''

        if( stock_info != ''):
            if( stock_info[-1] == ';'):
                stock_info = stock_info[0:-1]
            kospi_kosdaq = stock_info.split(';')[0].split('|')[1]
            yupjong = stock_info.split(';')[-1].split('|')[-1]
        return kospi_kosdaq + ':' + yupjong

    @Slot()
    def showAccountWindow(self):
        '''
        계좌비밀번호 입력창 출력
        '''
        return self.ocx.dynamicCall("KOA_Functions(QString, QString)", "ShowAccountWindow", [])

    @Slot(str, result=str)
    def getStockMarketKind(self, strCode):
        '''
        거래소 제도개선으로 주식 종목 중 정리매매/단기과열/투자위험/투자경고 종목을 매수주문하는 경우
        경고 메세지 창이 출력되도록 기능이 추가 되었습니다.
        (경고 창 출력 시 주문을 중지/전송 선택 가능합니다.)
        주문 함수를 호출하기 전에 특정 종목이 투자유의종목인지 아래와 같은 방법으로 확인할 수 있습니다.

        KOA_Functions("IsOrderWarningStock", "종목코드(6자리)")
        리턴 값 - "0":해당없음, "2":정리매매, "3":단기과열, "4":투자위험, "5":투자경고 
        '''
        return self.ocx.dynamicCall("KOA_Functions(QString, QString)", "IsOrderWarningStock", [strCode])

    @Slot(str, result=str)
    def getStockMarketKind(self, strCode):
        '''
        종목코드 입력으로 해당 종목이 어느 시장에 포함되어 있는지 구하는 기능
        서버와의 통신없이 메모리에 상주하는 값을 사용하므로 횟수제한 등은 없습니다. 사용법은 아래와 같습니다.
        
        KOA_Functions("GetStockMarketKind", "종목코드6자리");
        리턴값은 문자형으로 아래와 같습니다.
        "0":코스피, "10":코스닥, "3":ELW, "8":ETF, "4"/"14":뮤추얼펀드, "6"/"16":리츠, "9"/"19":하이일드펀드, "30":제3시장, "60":ETN
        '''
        return self.ocx.dynamicCall("KOA_Functions(QString, QString)", "GetStockMarketKind", [strCode])

if __name__ == "__main__":
    from kw_condition.utils import common_util

    myApp = QApplication(sys.argv)
    kw_obj = KiwoomOpenApiPlus()
    kw_obj.tryConnect()
    common_util.process_qt_events(kw_obj.isConnected,  60)


    # for index in range(1, 10):
    ########################################################################

    #     rqname = '주식기본정보요청'
    #     trcode = 'opt10001'
    #     screen_no = '000{}'.format(index)  # 화면번호, 0000 을 제외한 4자리 숫자 임의로 지정, None 의 경우 내부적으로 화면번호 자동할당

    #     inputs = {'종목코드': '005930'}

    #     kw_obj.add_transaction(rqname, trcode, inputs, screen_no)

    #     common_util.process_qt_events(kw_obj.has_transaction_result(rqname), 10)

    #     print( kw_obj.get_transaction_result(rqname) )

    ########################################################################
    # import datetime

    # rqname = '주식일봉차트조회요청'
    # trcode = 'opt10081'

    # current_time_str = datetime.datetime.now().strftime('%Y%m%d')

    # inputs = {'종목코드': '005930', '기준일자' : current_time_str, "수정주가구분": '1'}

    # kw_obj.add_transaction(rqname, trcode, inputs)

    # common_util.process_qt_events(kw_obj.has_transaction_result(rqname), 5)

    # # result 를 get 해야 다시 동일 rqname 으로 재요청 가능함 
    # daily_list = kw_obj.get_transaction_result(rqname)
    # # print( daily_list )


    # # 연속 조회 
    # rqname = '주식일봉차트조회요청'
    # trcode = 'opt10081'

    # current_time_str = datetime.datetime.now().strftime('%Y%m%d')

    # inputs = {'종목코드': '005930', '기준일자' : current_time_str, "수정주가구분": '1'}

    # kw_obj.add_transaction(rqname, trcode, inputs, prev_next= 2)

    # common_util.process_qt_events(kw_obj.has_transaction_result(rqname), 5)

    # # result 를 get 해야 다시 동일 rqname 으로 재요청 가능함 
    # daily_list.extend( kw_obj.get_transaction_result(rqname) )
    # # print( daily_list )


    ########################################################################
    # 전체종목 일봉 데이터 조회
    import datetime
    import pandas as pd

    current_time_str = datetime.datetime.now().strftime('%Y%m%d')

    for code in kw_obj.code_by_names.values():
        trcode = 'opt10081'
        stock_name = kw_obj.getMasterCodeName( code )
        rqname = '{}: 주식일봉차트조회요청'.format( stock_name ) 

        inputs = {'종목코드': '{}'.format( code ), '기준일자' : current_time_str, "수정주가구분": '1'}

        daily_list = []
        prev_next = 0

        while True:
            kw_obj.add_transaction(rqname, trcode, inputs, prev_next = prev_next)
            common_util.process_qt_events(kw_obj.has_transaction_result(rqname), 5)
            
            has_additional_data = kw_obj.has_transaction_additional_data(rqname)

            # result 를 get 해야 다시 동일 rqname 으로 재요청 가능함 
            daily_list.extend( kw_obj.get_transaction_result(rqname) )

            if( has_additional_data == True ):
                prev_next = 2
            else:

                daily_df = pd.DataFrame( daily_list, columns=["StockCode", "Date", "Open", "High", "Low", "Close", "Volume"] )     

                # 일봉 조회의 경우 종목 코드가 2번째 row 부터 공백이므로 삭제 
                daily_df.drop(columns='StockCode', axis =1, inplace = True)

                # string date -> datetime 
                daily_df['Date'] = pd.to_datetime( daily_df['Date'], format = '%Y%m%d') 

                # str to int
                selected_cols = ["Open", "High", "Low", "Close", "Volume"]
                daily_df[ selected_cols ] = daily_df[selected_cols].astype('int')

                daily_df = daily_df.set_index('Date')

                daily_df = daily_df.sort_values(by= 'Date')

                print(daily_df.head(2))

                # Excel 생성 
                daily_df.to_excel('{}.xlsx'.format( stock_name ) )
                break


    ########################################################################
    # kw_obj.load_condition_names()
    # common_util.process_qt_events(kw_obj.has_condition_names, 5)
    # print( kw_obj.get_condition_names() )
        
    sys.exit(myApp.exec_())
    pass