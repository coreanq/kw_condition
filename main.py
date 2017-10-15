# -*-coding: utf-8 -
import sys, os, re, datetime, copy, json
import xlwings as xw
import resource_rc

import util, kw_util

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl, QEvent
from PyQt5.QtCore import QStateMachine, QState, QTimer, QFinalState
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from mainwindow_ui import Ui_MainWindow

TEST_MODE = False    # 주의 TEST_MODE 를 True 로 하면 1주 단위로 삼 
# AUTO_TRADING_OPERATION_TIME = [ [ [9, 10], [10, 00] ], [ [14, 20], [15, 10] ] ]  # ex) 9시 10분 부터 10시까지 14시 20분부터 15시 10분 사이에만 동작 
AUTO_TRADING_OPERATION_TIME = [ [ [9, 1], [15, 19] ] ] #해당 시스템 동작 시간 설정 장시작시 급등하고 급락하여 매수 / 매도 시 손해 나는 것을 막기 위해 1분 유예 둠 (반드시 할것)

# DAY_TRADING_END_TIME 시간에 모두 시장가로 팔아 버림  반드시 동시 호가 시간 이전으로 입력해야함 
# auto_trading_operation_time 이전값을 잡아야 함 
DAY_TRADING_ENABLE = False
DAY_TRADING_END_TIME = [15, 10] 

TRADING_INFO_GETTING_TIME = [15, 35] # 트레이딩 정보를 저장하기 시작하는 시간

CONDITION_NAME = '급등' #키움증권 HTS 에서 설정한 조건 검색 식 총이름
TOTAL_BUY_AMOUNT = 10000000 #  매도 호가1, 2 총 수량이 TOTAL_BUY_AMOUNT 이상 안되면 매수금지  (슬리피지 최소화)


MAESU_BASE_UNIT = 100000 # 추가 매수 기본 단위 
SLIPPAGE = 0.5 # 보통가로 거래하므로 매매 수수료만 적용 
CHUMAE_TIME_LILMIT_HOURS  = 7  # 다음 추가 매수시 보내야될 시간 조건   장 운영 시간으로만 계산하므로 약 6.5 시간이 하루임 
TIME_CUT_MAX_DAY = 10  # 추가 매수 안한지 ?일 지나면 타임컷 수행하도록 함 

MAESU_LIMIT = 3 # 추가 매수 제한 
MAESU_TOTAL_PRICE =         [ MAESU_BASE_UNIT * 1,  MAESU_BASE_UNIT * 1,    MAESU_BASE_UNIT * 2,    MAESU_BASE_UNIT * 4,    MAESU_BASE_UNIT * 8 ]
# 추가 매수 진행시 stoploss 및 stopplus 퍼센티지 변경 최대 6
STOP_PLUS_PER_MAESU_COUNT = [ 8,                    8,                      8,                      8,                      8                  ]
STOP_LOSS_PER_MAESU_COUNT = [ 40,                   40,                     40,                     40,                     40,                ]

TR_TIME_LIMIT_MS = 3800 # 키움 증권에서 정의한 연속 TR 시 필요 딜레이 

EXCEPTION_LIST = [] # 장기 보유 종목 번호 리스트  ex) EXCEPTION_LIST = ['034220'] 
STOCK_POSSESION_COUNT = 20 + len(EXCEPTION_LIST)   # 보유 종목수 제한 

CHEGYEOL_INFO_FILE_PATH = "log" + os.path.sep +  "chegyeol.json"
JANGO_INFO_FILE_PATH =  "log" + os.path.sep + "jango.json"
CHEGYEOL_INFO_EXCEL_FILE_PATH = "log" + os.path.sep +  "chegyeol.xlsx"

class CloseEventEater(QObject):
    def eventFilter(self, obj, event):
        if( event.type() == QEvent.Close):
            test_make_jangoInfo()
            return True
        else:
            return super(CloseEventEater, self).eventFilter(obj, event)

class KiwoomConditon(QObject):
    sigInitOk = pyqtSignal()
    sigConnected = pyqtSignal()
    sigDisconnected = pyqtSignal()
    sigTryConnect = pyqtSignal()
    sigGetConditionCplt = pyqtSignal()
    sigSelectCondition = pyqtSignal()
    sigWaitingTrade = pyqtSignal()
    sigRefreshCondition = pyqtSignal()

    sigStateStop = pyqtSignal()
    sigStockComplete = pyqtSignal()

    sigConditionOccur = pyqtSignal()
    sigRequestInfo = pyqtSignal()
    sigRequestEtcInfo = pyqtSignal()

    sigGetBasicInfo = pyqtSignal()
    sigGetEtcInfo = pyqtSignal()
    sigGet5minInfo = pyqtSignal()
    sigGetHogaInfo = pyqtSignal()
    sigTrWaitComplete = pyqtSignal()

    sigBuy = pyqtSignal()
    sigNoBuy = pyqtSignal()
    sigRequestRealHogaComplete = pyqtSignal()
    sigError = pyqtSignal()
    sigRequestJangoComplete = pyqtSignal()
    sigCalculateStoplossComplete = pyqtSignal()
    sigStartProcessBuy = pyqtSignal()
    sigStopProcessBuy = pyqtSignal()
    sigTerminating = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.fsm = QStateMachine()
        self.account_list = []
        self.timerSystem = QTimer()
        self.lineCmdText = ''

        self.todayTradedCodeList = [] # 금일 거래 되었던 종목 

        self.yupjongInfo = {'코스피': {}, '코스닥': {} } # { 'yupjong_code': { '현재가': 222, ...} }
        self.michegyeolInfo = {}
        self.jangoInfo = {} # { 'jongmokCode': { '이익실현가': 222, ...}}
        self.jangoInfoFromFile = {} # TR 잔고 정보 요청 조회로는 얻을 수 없는 데이터를 파일로 저장하고 첫 실행시 로드함  
        self.chegyeolInfo = {} # { '날짜' : [ [ '주문구분', '매도', '주문/체결시간', '체결가' , '체결수량', '미체결수량'] ] }
        self.conditionOccurList = [] # 조건 진입이 발생한 모든 리스트 저장하고 매수 결정에 사용되는 모든 정보를 저장함  [ {'종목코드': code, ...}] 
        self.conditionRevemoList = [] # 조건 이탈이 발생한 모든 리스트 저장 

        self.kospiCodeList = () 
        self.kosdaqCodeList = () 

        self.createState()
        self.createConnection()
        self.currentTime = datetime.datetime.now()
        
    def createState(self):
        # state defintion
        mainState = QState(self.fsm)       
        stockCompleteState = QState(self.fsm)
        finalState = QFinalState(self.fsm)
        self.fsm.setInitialState(mainState)
        
        initState = QState(mainState)
        disconnectedState = QState(mainState)
        connectedState = QState(QtCore.QState.ParallelStates, mainState)

        systemState = QState(connectedState)
        
        initSystemState = QState(systemState)
        waitingTradeSystemState = QState(systemState)
        standbySystemState = QState(systemState)
        requestingJangoSystemState = QState(systemState)
        calculateStoplossSystemState = QState(systemState)
        terminatingSystemState = QState(systemState)
        
        #transition defition
        mainState.setInitialState(initState)
        mainState.addTransition(self.sigStateStop, finalState)
        mainState.addTransition(self.sigStockComplete, stockCompleteState)
        stockCompleteState.addTransition(self.sigStateStop, finalState)
        initState.addTransition(self.sigInitOk, disconnectedState)
        disconnectedState.addTransition(self.sigConnected, connectedState)
        disconnectedState.addTransition(self.sigTryConnect, disconnectedState)
        connectedState.addTransition(self.sigDisconnected, disconnectedState)
        
        systemState.setInitialState(initSystemState)
        initSystemState.addTransition(self.sigGetConditionCplt, requestingJangoSystemState)
        requestingJangoSystemState.addTransition(self.sigRequestJangoComplete, calculateStoplossSystemState)
        calculateStoplossSystemState.addTransition(self.sigCalculateStoplossComplete, waitingTradeSystemState)

        waitingTradeSystemState.addTransition(self.sigWaitingTrade, waitingTradeSystemState )
        waitingTradeSystemState.addTransition(self.sigSelectCondition, standbySystemState)

        standbySystemState.addTransition(self.sigRefreshCondition, initSystemState)
        standbySystemState.addTransition(self.sigTerminating,  terminatingSystemState )
        
        #state entered slot connect
        mainState.entered.connect(self.mainStateEntered)
        stockCompleteState.entered.connect(self.stockCompleteStateEntered)
        initState.entered.connect(self.initStateEntered)
        disconnectedState.entered.connect(self.disconnectedStateEntered)
        connectedState.entered.connect(self.connectedStateEntered)
        
        systemState.entered.connect(self.systemStateEntered)
        initSystemState.entered.connect(self.initSystemStateEntered)
        waitingTradeSystemState.entered.connect(self.waitingTradeSystemStateEntered)
        requestingJangoSystemState.entered.connect(self.requestingJangoSystemStateEntered)
        calculateStoplossSystemState.entered.connect(self.calculateStoplossPlusStateEntered)
        standbySystemState.entered.connect(self.standbySystemStateEntered)
        terminatingSystemState.entered.connect(self.terminatingSystemStateEntered)
    
        # processBuy definition
        processBuyState = QState(connectedState)
        initProcessBuyState = QState(processBuyState)
        standbyProcessBuyState = QState(processBuyState)
        requestEtcInfoProcessBuyState = QState(processBuyState)
        request5minInfoProcessBuyState = QState(processBuyState)
        determineBuyProcessBuyState = QState(processBuyState)
        waitingTRlimitProcessBuyState = QState(processBuyState)

        processBuyState.setInitialState(initProcessBuyState)
        initProcessBuyState.addTransition(self.sigStartProcessBuy, standbyProcessBuyState)

        standbyProcessBuyState.addTransition(self.sigConditionOccur, standbyProcessBuyState)
        standbyProcessBuyState.addTransition(self.sigRequestEtcInfo, requestEtcInfoProcessBuyState)
        standbyProcessBuyState.addTransition(self.sigStopProcessBuy, initProcessBuyState)

        requestEtcInfoProcessBuyState.addTransition(self.sigGetEtcInfo, waitingTRlimitProcessBuyState)
        requestEtcInfoProcessBuyState.addTransition(self.sigRequestInfo, request5minInfoProcessBuyState)
        requestEtcInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState )

        request5minInfoProcessBuyState.addTransition(self.sigGet5minInfo, determineBuyProcessBuyState)
        request5minInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState )

        determineBuyProcessBuyState.addTransition(self.sigNoBuy, waitingTRlimitProcessBuyState)
        determineBuyProcessBuyState.addTransition(self.sigBuy, waitingTRlimitProcessBuyState)

        waitingTRlimitProcessBuyState.addTransition(self.sigTrWaitComplete, standbyProcessBuyState)

        processBuyState.entered.connect(self.processBuyStateEntered)
        initProcessBuyState.entered.connect(self.initProcessBuyStateEntered)
        standbyProcessBuyState.entered.connect(self.standbyProcessBuyStateEntered)
        requestEtcInfoProcessBuyState.entered.connect(self.requestEtcInfoProcessBuyStateEntered)
        request5minInfoProcessBuyState.entered.connect(self.request5minInfoProcessBuyStateEntered)
        determineBuyProcessBuyState.entered.connect(self.determineBuyProcessBuyStateEntered)
        waitingTRlimitProcessBuyState.entered.connect(self.waitingTRlimitProcessBuyStateEntered)
                
        #fsm start
        finalState.entered.connect(self.finalStateEntered)
        self.fsm.start()

        pass

    def initQmlEngine(self):
        self.qmlEngine.load(QUrl('qrc:///qml/main.qml'))        
        self.rootObject = self.qmlEngine.rootObjects()[0]
        self.rootObject.startClicked.connect(self.onStartClicked)
        self.rootObject.restartClicked.connect(self.onRestartClicked)
        self.rootObject.requestJangoClicked.connect(self.onRequestJangoClicked)
        self.rootObject.chegyeolClicked.connect(self.onChegyeolClicked)
        self.rootObject.testClicked.connect(self.onTestClicked)

        rootContext = self.qmlEngine.rootContext()
        rootContext.setContextProperty("model", self)
        pass
    @pyqtSlot()
    def onBtnMakeExcelClicked(self):
        print(util.whoami())
        self.make_excel(CHEGYEOL_INFO_EXCEL_FILE_PATH, self.chegyeolInfo)
        pass
    @pyqtSlot()
    def onBtnStartClicked(self):
        print(util.whoami())
        self.sigInitOk.emit()
        
    @pyqtSlot()
    def onBtnJangoClicked(self):
        self.printStockInfo()

    @pyqtSlot()
    def onBtnYupjongClicked(self):
        self.printYupjongInfo()
        pass

    @pyqtSlot()
    def onBtnChegyeolClicked(self):
        self.printChegyeolInfo('all')

    @pyqtSlot()
    def onBtnRunClicked(self):
        arg = self.lineCmdText
        if( arg ):
            eval(arg)
        pass

    @pyqtSlot()
    def onBtnConditionClicked(self):
        items = self.getCodeListConditionOccurList()
        buffer = [] 

        for item in items: 
            boyou = "보유" if item in self.jangoInfo else ""
            log_string = "{} {} ({})".format(item,  self.getMasterCodeName(item), boyou) 

            if( boyou == "보유" ):
                buffer.append(log_string)
            else:
                buffer.insert(0, log_string)
        
        print( '\n'.join(buffer) )
        pass
    
    @pyqtSlot(str)
    def onLineCmdTextChanged(self, str):
        self.lineCmdText = str
        pass

    @pyqtSlot(str)
    def onTestClicked(self, arg):
        print(util.whoami() + ' ' + arg)
        eval(arg)
        pass

    def createConnection(self):
        self.ocx.OnEventConnect[int].connect(self._OnEventConnect)
        self.ocx.OnReceiveMsg[str, str, str, str].connect(self._OnReceiveMsg)
        self.ocx.OnReceiveTrData[str, str, str, str, str,
                                    int, str, str, str].connect(self._OnReceiveTrData)
        self.ocx.OnReceiveRealData[str, str, str].connect(
            self._OnReceiveRealData)
        self.ocx.OnReceiveChejanData[str, int, str].connect(
            self._OnReceiveChejanData)
        self.ocx.OnReceiveConditionVer[int, str].connect(
            self._OnReceiveConditionVer)
        self.ocx.OnReceiveTrCondition[str, str, str, int, int].connect(
            self._OnReceiveTrCondition)
        self.ocx.OnReceiveRealCondition[str, str, str, str].connect(
            self._OnReceiveRealCondition)

        self.timerSystem.setInterval(1000) 
        self.timerSystem.timeout.connect(self.onTimerSystemTimeout) 

    def isTradeAvailable(self):
        # 시간을 확인해 거래 가능한지 여부 판단 
        ret_vals= []
        current_time = self.currentTime.time()
        for start, stop in AUTO_TRADING_OPERATION_TIME:
            start_time =  datetime.time(
                            hour = start[0],
                            minute = start[1])
            stop_time =   datetime.time( 
                            hour = stop[0],
                            minute = stop[1])
            if( current_time >= start_time and current_time <= stop_time ):
                ret_vals.append(True)
            else:
                ret_vals.append(False)
                pass

        # 하나라도 True 였으면 거래 가능시간임  
        if( ret_vals.count(True) ):
            return True
        else:
            return False
        pass
  
    @pyqtSlot()
    def mainStateEntered(self):
        pass

    @pyqtSlot()
    def stockCompleteStateEntered(self):
        print(util.whoami())
        self.sigStateStop.emit()
        pass

    @pyqtSlot()
    def initStateEntered(self):
        print(util.whoami())
        self.sigInitOk.emit()
        pass

    @pyqtSlot()
    def disconnectedStateEntered(self):
        # print(util.whoami())
        if( self.getConnectState() == 0 ):
            self.commConnect()
            QTimer.singleShot(90000, self.sigTryConnect)
            pass
        else:
            self.sigConnected.emit()
            
    @pyqtSlot()
    def connectedStateEntered(self):
        # get 계좌 정보

        account_cnt = self.getLoginInfo("ACCOUNT_CNT")
        acc_num = self.getLoginInfo("ACCNO")
        user_id = self.getLoginInfo("USER_ID")
        user_name = self.getLoginInfo("USER_NAME")
        keyboard_boan = self.getLoginInfo("KEY_BSECGB")
        firewall = self.getLoginInfo("FIREW_SECGB")
        print("account count: {}, acc_num: {}, user id: {}, " 
              "user_name: {}, keyboard_boan: {}, firewall: {}"
              .format(account_cnt, acc_num, user_id, user_name, 
                      keyboard_boan, firewall))

        self.account_list = (acc_num.split(';')[:-1])

        print(util.whoami() + 'account list ' + str(self.account_list))

        # 코스피 , 코스닥 종목 코드 리스트 얻기 
        result = self.getCodeListByMarket('0')
        self.kospiCodeList = tuple(result.split(';'))
        result = self.getCodeListByMarket('10')
        self.kosdaqCodeList = tuple(result.split(';'))
        pass

    @pyqtSlot()
    def systemStateEntered(self):
        pass

    @pyqtSlot()
    def initSystemStateEntered(self):
        # 체결정보 로드 
        if( os.path.isfile(CHEGYEOL_INFO_FILE_PATH) == True ):
            with open(CHEGYEOL_INFO_FILE_PATH, 'r', encoding='utf8') as f:
                file_contents = f.read()
                self.chegyeolInfo = json.loads(file_contents)
            # 금일 체결 정보는 매수 금지 리스트로 추가함 
            for trade_date, data_chunk in self.chegyeolInfo.items():
                if( datetime.datetime.strptime(trade_date, "%y%m%d").date() == self.currentTime.date() ): 
                    for trade_info in data_chunk: 
                        parse_str_list = [item.strip() for item in trade_info.split('|') ] 
                        if( len(parse_str_list)  < 5):
                            continue
                        jongmok_code_index = kw_util.dict_jusik['체결정보'].index('종목코드')
                        jumun_gubun_index = kw_util.dict_jusik['체결정보'].index('주문구분')

                        jongmok_code = parse_str_list[jongmok_code_index]
                        jumun_gubun  = parse_str_list[jumun_gubun_index]

                        if( jumun_gubun == "-매도"):
                            self.todayTradedCodeList.append(jongmok_code)
                    break

        if( os.path.isfile(JANGO_INFO_FILE_PATH) == True ):
            with open(JANGO_INFO_FILE_PATH, 'r', encoding='utf8') as f:
                file_contents = f.read()
                self.jangoInfoFromFile = json.loads(file_contents)

        # get 조건 검색 리스트
        self.getConditionLoad()
        self.setRealReg(kw_util.sendRealRegUpjongScrNo, '1;101', kw_util.type_fidset['업종지수'], "0")
        self.setRealReg(kw_util.sendRealRegTradeStartScrNo, '', kw_util.type_fidset['장시작시간'], "0")
        self.timerSystem.start()
        pass

    @pyqtSlot()
    def waitingTradeSystemStateEntered(self):
        # 장시작 전에 조건이 시작하도록 함 
        time_span = datetime.timedelta(minutes = 40)
        expected_time = (self.currentTime + time_span).time()
        if( expected_time >= datetime.time(*AUTO_TRADING_OPERATION_TIME[0][0]) ):
            self.sigSelectCondition.emit()       

            # 반환값 : 조건인덱스1^조건명1;조건인덱스2^조건명2;…;
            # result = '조건인덱스1^조건명1;조건인덱스2^조건명2;'
            result = self.getConditionNameList()
            searchPattern = r'(?P<index>[^\/:*?"<>|;]+)\^(?P<name>[^\/:*?"<>|;]+);'
            fileSearchObj = re.compile(searchPattern, re.IGNORECASE)
            findList = fileSearchObj.findall(result)
            
            tempDict = dict(findList)
            print(tempDict)
            
            condition_num = 0 
            for number, condition in tempDict.items():
                if condition == CONDITION_NAME:
                        condition_num = int(number)
            print("select condition" + kw_util.sendConditionScreenNo, CONDITION_NAME)
            self.sendCondition(kw_util.sendConditionScreenNo, CONDITION_NAME, condition_num,   1)

            
        else:
            QTimer.singleShot(1000, self.sigWaitingTrade)

        pass

    @pyqtSlot()
    def requestingJangoSystemStateEntered(self):
        # print(util.whoami() )
        self.requestOpw00018(self.account_list[0])
        pass 
    
    @pyqtSlot()
    def calculateStoplossPlusStateEntered(self):
        # print(util.whoami() )
        # 이곳으로 온 경우 이미 잔고 TR 은 요청한 상태임 
        for jongmok_code in self.jangoInfo:
            self.makeEtcJangoInfo(jongmok_code)
        self.makeJangoInfoFile()
        self.sigCalculateStoplossComplete.emit()

    @pyqtSlot()
    def standbySystemStateEntered(self):
        print(util.whoami() )
        # 프로그램 첫 시작시 TR 요청으로 인한 제한 시간  막기 위해 딜레이 줌 
        QTimer.singleShot(TR_TIME_LIMIT_MS * 5, self.sigStartProcessBuy)
        pass

    @pyqtSlot()
    def terminatingSystemStateEntered(self):
        print(util.whoami() )
        pass


    @pyqtSlot()
    def processBuyStateEntered(self):
        pass
     
    @pyqtSlot()
    def initProcessBuyStateEntered(self):
        print(util.whoami())
        pass

    @pyqtSlot()
    def standbyProcessBuyStateEntered(self):
        # print(util.whoami() )
        # 운영 시간이 아닌 경우 운영시간이 될때까지 지속적으로 확인 
        if( self.isTradeAvailable() == False ):
            print(util.whoami() )
            QTimer.singleShot(10000, self.sigConditionOccur)
            return
        else:
            # 무한으로 시그널 발생 방지를 위해 딜레이 줌
            QTimer.singleShot(100, self.sigRequestEtcInfo)

    @pyqtSlot()
    def requestEtcInfoProcessBuyStateEntered(self):
        # print(util.whoami())
        # if( '5분 0봉전' not in self.yupjongInfo['코스피']):
        #     self.requestOpt20005('001')
        #     return
        # elif ( '5분 0봉전' not in self.yupjongInfo['코스닥']):
        #     self.requestOpt20005('101')
        #     return

        # 5분마다 업종 정보를 다시 요청하도록 함 
        # time_span = datetime.timedelta(minutes = 5)

        # chegyeol_index = kw_util.dict_jusik['TR:업종분봉'].index('체결시간')
        # chegyeol_time_str = self.yupjongInfo['코스피']['5분 0봉전'][chegyeol_index]   #20170502140359 
        # target_time = datetime.datetime.strptime(chegyeol_time_str, "%Y%m%d%H%M%S") + time_span
        
        # if( datetime.datetime.now() > target_time ):
        #     self.requestOpt20005('001')
        #     return

        # chegyeol_time_str = self.yupjongInfo['코스닥']['5분 0봉전'][chegyeol_index]   #20170502140359 
        # target_time = datetime.datetime.strptime(chegyeol_time_str, "%Y%m%d%H%M%S") + time_span

        # if( datetime.datetime.now() > target_time ):
        #     self.requestOpt20005('101')
        #     return

        # 조건 발생 리스트 검색 
        for jongmok_code in self.conditionRevemoList:
            self.removeConditionOccurList(jongmok_code)
        self.conditionRevemoList.clear()

        self.refreshRealRequest()

        jongmok_info = self.getConditionOccurList()

        if( jongmok_info ):
            jongmok_code = jongmok_info['종목코드']
            jongmok_name = jongmok_info['종목명'] 
            if( '상한가' not in jongmok_info):
                self.requestOpt10001(jongmok_code)
            else:
                self.sigRequestInfo.emit()
            # print(util.whoami() , jongmok_name, jongmok_code ) 
            return
        else:
            self.sigError.emit()
        pass

    @pyqtSlot()
    def request5minInfoProcessBuyStateEntered(self):
        # print(util.whoami() )
        jongmok_info_dict = self.getConditionOccurList()   

        if( not jongmok_info_dict ):
            self.shuffleConditionOccurList()
            self.sigError.emit()
            return 

        code = jongmok_info_dict['종목코드']
        # 아직 실시간 정보를 못받아온 상태라면 
        # 체결 정보 받는데 시간 걸리므로 다른 종목 폴링 
        # 혹은 집입했닥 이탈하면 데이터 삭제 하므로 실시간 정보가 없을수도 있다. 
        if( '매도호가1' not in jongmok_info_dict or '등락율' not in jongmok_info_dict ):
            self.shuffleConditionOccurList()
            if( '매도호가1' not in jongmok_info_dict ):
                print('매도호가1 not in {0}'.format(code))
            else:
                print('등락율 not in {0}'.format(code))
            self.sigError.emit()
            return

        if( self.requestOpt10080(code) == False ):
            self.sigError.emit()

        pass

    @pyqtSlot()
    def determineBuyProcessBuyStateEntered(self):
        print('!', end='')
        jongmok_info_dict = []
        is_log_print_enable = False
        return_vals = []
        printLog = ''

        jongmok_info_dict = self.getConditionOccurList()   
        if( jongmok_info_dict ):
            pass
        else:
            printLog += '(조건리스트없음)'
            self.sigNoBuy.emit()
            return
            
        jongmokCode = jongmok_info_dict['종목코드']
        jongmokName = jongmok_info_dict['종목명']

        # 호가 정보는 문자열로 기준가 대비 + , - 값이 붙어 나옴 
        maedoHoga1 =  abs(int(jongmok_info_dict['매도호가1']))
        maedoHogaAmount1 =  int(jongmok_info_dict['매도호가수량1'])
        maedoHoga2 =  abs(int(jongmok_info_dict['매도호가2']) )
        maedoHogaAmount2 =  int(jongmok_info_dict['매도호가수량2']) 
        # print( util.whoami() +  maedoHoga1 + " " + maedoHogaAmount1 + " " + maedoHoga2 + " " + maedoHogaAmount2 )
        # print( util.whoami() + jongmokName + " " + str(sum) + (" won") ) 
        # util.save_log( '{0:^20} 호가1:{1:>8}, 잔량1:{2:>8} / 호가2:{3:>8}, 잔량2:{4:>8}'
                # .format(jongmokName, maedoHoga1, maedoHogaAmount1, maedoHoga2, maedoHogaAmount2), '호가잔량' , folder= "log") 

        printLog += ' ' + jongmokName + ' '  + jongmokCode + ' ' + str(maedoHoga1) + ' '

        ##########################################################################################################
        # 제외 종목인지 확인 
        if( jongmokCode in EXCEPTION_LIST ):
            printLog += "(제외종목)"
            return_vals.append(False)

        ##########################################################################################################
        # 최대 보유 할 수 있는 종목 보유수를 넘었는지 확인 
        if( len(self.jangoInfo.keys()) < STOCK_POSSESION_COUNT ):
            pass
        else:
            if( jongmokCode not in self.jangoInfo):
                printLog += "(종목최대보유중)"
                return_vals.append(False)

        ##########################################################################################################
        # 거래 가능시간인지 체크 
        if( self.isTradeAvailable() ):  
            pass
        else:
            printLog += "(거래시간X)"
            return_vals.append(False)


        
        ##########################################################################################################
        # 가격 및 거래량 정보 생성 
        amount_index = kw_util.dict_jusik['TR:분봉'].index('거래량')
        current_price_index =  kw_util.dict_jusik['TR:분봉'].index('현재가')

        before_prices = []
        before_amounts = []
        five_min_template = '5분 {}봉전'

        for index in range(200):
            five_min_str = five_min_template.format(index)
            if(five_min_str in jongmok_info_dict ):
                price = abs(int(jongmok_info_dict[five_min_str][current_price_index]))
                amount = abs(int(jongmok_info_dict[five_min_str][amount_index]))
                before_amounts.append(amount)
                before_prices.append(price)
        
        # printLog += '(5분봉: 거래량 {0}% 0: price({1}/{2}), 1: ({3}/{4})'.format(
        #     int(before_amounts[0] / before_amounts[1] * 100), 
        #     before_prices[0], before_amounts[0], 
        #     before_prices[1], before_amounts[1]
        #     )

        ##########################################################################################################
        # 최근 매수가 정보 생성
        last_maeip_price = 99999999
        if( jongmokCode in self.jangoInfo):
            last_maeip_price = int(self.jangoInfo[jongmokCode]['최근매수가'][-1])
        

        ##########################################################################################################
        # 얼마 이상 거래 되었을 시 --->  거래량이 너무 최소인 경우를 막기 위함
        # 최근 매입가보다 낮은 경우만 매수 
        if( 
            before_amounts[0] * maedoHoga1 > 100000000 and            
            maedoHoga1 <  last_maeip_price           
            ):
            pass
        else:
            printLog += ('(5분봉거래금액미충족:{})'.format( before_amounts[0] * maedoHoga1 ) )
            return_vals.append(False)

        ##########################################################################################################
        # 추가 매수 시간 제한  
        if( jongmokCode in self.jangoInfo):
            chegyeol_time_str = self.jangoInfo[jongmokCode]['주문/체결시간'][-1] #20170411151000
            target_time_index = kw_util.dict_jusik['TR:분봉'].index('체결시간')
            fivemin_time_str = '5분 {0}봉전'.format(CHUMAE_TIME_LILMIT_HOURS * 12)
            target_time_str = jongmok_info_dict[fivemin_time_str][target_time_index] 

            if( chegyeol_time_str != ''):
                chegyeol_time = datetime.datetime.strptime(chegyeol_time_str, "%Y%m%d%H%M%S") 
                target_time = datetime.datetime.strptime(target_time_str, "%Y%m%d%H%M%S") 
                # print('체결:{0}, 타겟:{1}'.format( chegyeol_time_str, target_time_str))
                if( chegyeol_time < target_time ):
                    pass
                else:
                    printLog += '(추가매수금지)'
                    return_vals.append(False)

        ##########################################################################################################
        #  추가 매수 횟수 제한   
        maesu_count = 0 
        if( jongmokCode in self.jangoInfo):
            maesu_count = self.jangoInfo[jongmokCode]['매수횟수']
        if( maesu_count + 1 <= MAESU_LIMIT ):
            pass
        else:
            printLog += '(추가매수한계)'
            return_vals.append(False)

        ##########################################################################################################
        # 개별 주식 이동평균선 조건 판단 첫 매수시는 그냥 사고 추가 매수시는 200봉 평균보다 높은 경우 삼
        # 매수후 지속적으로 하락 시 (200봉 평균보다 낮은 경우 계속 발생) 사지 않도록 함  
        rsi_14 = int( float(jongmok_info_dict['RSI14']) )
        totalAmount = maedoHoga1 * maedoHogaAmount1 + maedoHoga2 * maedoHogaAmount2

        ##########################################################################################################
        # 첫 매수시 
        if( jongmokCode not in self.jangoInfo ):
            if( before_amounts[0]> before_amounts[1] * 2 ): # 첫 매수는 거래량 조건 보기 
                pass
            else:
                printLog += '(첫매수거래량조건미충족)'
                return_vals.append(False)

        ##########################################################################################################
        # 매도 호가 잔량지 확인해  살만큼 있는 경우 추가 매수때는 급등인 경우 많아 볼면 안됨 
            if( totalAmount >= TOTAL_BUY_AMOUNT):
                pass 
            else:
                printLog += '(호가수량부족: 매도호가1 {0} 매도호가잔량1 {1})'.format(maedoHoga1, maedoHogaAmount1)
                return_vals.append(False)
            pass

        ##########################################################################################################
        # 추가 매수시 
        else:
            maeip_price = self.jangoInfo[jongmokCode]['매입가']
            # 조건 없이 사지는 것이므로 호가 잔량 확인함 
            if( maeip_price * 0.7 >  maedoHoga1 ):
                if( totalAmount >= TOTAL_BUY_AMOUNT):
                    pass 
                else:
                    printLog += '(-30호가수량부족: 매도호가1 {0} 매도호가잔량1 {1})'.format(maedoHoga1, maedoHogaAmount1)
                    util.save_log(printLog, '\t\t', folder = "log")
                    return_vals.append(False)
                pass

            elif ( maeip_price * 0.85 > maedoHoga1 ):
                twohundred_avr = jongmok_info_dict['200봉0평균'] 
                # 현재가가 이평보다 낮은 경우 제외
                if(  twohundred_avr > maedoHoga1 ):   
                    # printLog += ('(200봉:{} > 현재가: {})'.format( twohundred_avr, maedoHoga1) )
                    return_vals.append(False)
                else:
                    # 1,2, 봉까지는 무시 이전 봉들이 200평 아래 있다가 갑자기 오른 경우 
                    for count in range(3, 156):
                        twohundred_avr = jongmok_info_dict['200봉{}평균'.format(count)] 
                        if( before_prices[count] > twohundred_avr ):
                            printLog += '(최근5분200이평미충족)'
                            util.save_log(printLog, '\t\t', folder = "log")
                            return_vals.append(False)
                            break
            else:
                printLog += '(수익률미충족)'
                return_vals.append(False)
        
            temp = '({} {})'\
                .format( jongmokName,  maedoHoga1 )
            print( util.cur_time_msec() , temp)
            printLog += temp

      


        ##########################################################################################################
        # 업종 이동 평균선 조건 상승일때 매수  
        # if( jongmokCode in  self.kospiCodeList):
        #     yupjong_name = '코스피'
        #     twentybong_avr = float(self.yupjongInfo[yupjong_name]['20봉평균'])
        #     fivebong_avr = float(self.yupjongInfo[yupjong_name]['5봉평균'])
        #     if( fivebong_avr > twentybong_avr ):
        #         printLog +='({0}이평조건충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
        #     else:
        #         printLog +='({0}이평조건미충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
        #         return_vals.append(False)
        #     pass
        # else: 
        #     yupjong_name = '코스닥'
        #     twentybong_avr = float(self.yupjongInfo[yupjong_name]['20봉평균'])
        #     fivebong_avr = float(self.yupjongInfo[yupjong_name]['5봉평균'])
        #     if( fivebong_avr > twentybong_avr ):
        #         printLog +='({0}이평조건충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
        #     else:
        #         printLog +='({0}이평조건미충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
        #         return_vals.append(False)
        #     pass

        ##########################################################################################################
        # 가격조건 확인 
        # if( maedoHoga1 >= STOCK_PRICE_MIN_MAX['min'] and maedoHoga1 <= ['max']):
        #     pass
        # else:
        #     printLog += '(종목가격미충족: 매도호가1 {0})'.format(maedoHoga1)
        #     return_vals.append(False)
        

        ##########################################################################################################
        # 종목 등락율을 확인해 너무 급등한 종목은 사지 않도록 함 
        # 가격이 많이 오르지 않은 경우 앞에 +, - 붙는 소수이므로 float 으로 먼저 처리 
        # updown_percentage = float(jongmok_info_dict['등락율'] )
        # if( updown_percentage <= 30 - STOP_PLUS_VALUE * 5 ):
        #     pass
        # else:
        #     printLog += '(종목등락율미충족: 등락율 {0})'.format(updown_percentage)
        #     return_vals.append(False)


        ##########################################################################################################
        # 이미 보유한 종목 구매 금지 
        # if( jongmokCode not in self.jangoInfo) ):
        #     pass
        # else:
        #     printLog += '(____기보유종목____: {0})'.format(jongmokName)
        #     return_vals.append(False)
        #     pass


        ##########################################################################################################
        # 업종 등락율을 살펴서 보합 상승을 제외 - 면 사지 않음 :
        # if( jongmokCode in  self.kospiCodeList):
        #     updown_percentage = float(self.yupjongInfo['코스피'].get('등락율', -99) )
        #     if( updown_percentage < -0.2 ) :
        #         printLog +='(코스피등락율미충족: 등락율 {0})'.format(updown_percentage)
        #         return_vals.append(False)
        #     pass
        # else: 
        #     updown_percentage = float(self.yupjongInfo['코스닥'].get('등락율', -99) )
        #     if( updown_percentage < -0.2 ) :
        #         printLog +='(코스닥등락율미충족: 등락율 {0})'.format(updown_percentage)
        #         return_vals.append(False)


        ##########################################################################################################
        # 시작가 조건 확인 너무 높은 시작가는 급락을 야기함  
        # jeonil_daebi = int(jongmok_info_dict['전일대비'])
        # current_price = int(jongmok_info_dict['현재가'])

        # base_price = current_price - jeonil_daebi 
        # start_price = int(jongmok_info_dict['시가'])
        # start_price_percent = int((start_price / base_price - 1) * 100)
        # if( start_price_percent <= 5 ):
        #     pass
        # else:
        #     printLog += '(시작가등락율미충족 등락율:{0}% 시가:{1} )'.format(start_price_percent, start_price)
        #     return_vals.append(False)


        ##########################################################################################################
        # 현재가가 시가보다 낮은 경우제외 (급등후 마이너스 달리는 종목) 
        # 장초반 살때 음봉에서 사는것을 막기 위함 
        # current_price = maedoHoga1
        # if( start_price < current_price ):
        #     pass
        # else:
        #     printLog += '((시작가 > 현재가 시가:{0}, 현재가:{1} )'.format(start_price, current_price )
        #     return_vals.append(False)

        # print(json.dumps(jongmok_info_dict, ensure_ascii= False, indent = 2, sort_keys = True))


        ##########################################################################################################
        # 가격 형성이 당일 고가 근처인 종목만 매수
        # high_price  = int(jongmok_info_dict['고가'])
        # current_price = int( maedoHoga1) 

        # if( high_price <= current_price ):
        #     pass
        # else:
        #     printLog += '(고가조건 미충족: 현재가:{0} 고가:{1} )'.format(current_price, high_price)
        #     return_vals.append(False)


        ##########################################################################################################
        # 저가가 전일종가 밑으로 내려간적 있는 지 확인 
        # low_price = int(jongmok_info_dict['저가'])
        # if( low_price >= base_price ):
        #     pass
        # else:
        #     printLog += '(저가가전일종가보다낮음)'
        #     return_vals.append(False)


        ##########################################################################################################
        # 기존에 이미 매도 발생한 종목이라면  
        # if( self.todayTradedCodeList.count(jongmokCode) == 0 ):
        #     pass
        # else:
        #     printLog += '(금일거래종목)'
        #     return_vals.append(False)

        # 매수 
        if( return_vals.count(False) == 0 ):
            util.save_log(jongmokName, '매수주문', folder= "log")
            qty = 0
            if( TEST_MODE == True ):
                qty = MAESU_TOTAL_PRICE[maesu_count] / MAESU_BASE_UNIT 
            else:
                # 매수 수량을 조절하기 위함 
                if( jongmokCode in self.jangoInfo):
                    chegyeol_time_list = self.jangoInfo[jongmokCode].get('주문/체결시간', [])
                    first_chegyeol_time_str = ""
                    if( len(chegyeol_time_list ) ):
                        first_chegyeol_time_str = chegyeol_time_list[0]

                    if( first_chegyeol_time_str != ''):
                        base_time = datetime.datetime.strptime("20170830102400", "%Y%m%d%H%M%S") 

                        first_maesu_time = datetime.datetime.strptime(first_chegyeol_time_str, "%Y%m%d%H%M%S") 
                        total_price = MAESU_TOTAL_PRICE[maesu_count] 
                        if( base_time  < first_maesu_time ):
                            qty = int(total_price / maedoHoga1/2 ) + 1 #  약간 오버하게 삼 
                            pass
                        else:
                            qty = int(total_price / maedoHoga1 ) + 1
                else:
                    total_price = MAESU_TOTAL_PRICE[maesu_count] 
                    qty = int(total_price / maedoHoga1 /2 ) + 1


            result = self.sendOrder("buy_" + jongmokCode, kw_util.sendOrderScreenNo, 
                                objKiwoom.account_list[0], kw_util.dict_order["신규매수"], jongmokCode, 
                                qty, 0 , kw_util.dict_order["시장가"], "")

            print("B " + str(result) , sep="")
            printLog = '**** [매수수량: {0}, 매수가: {1}, 매수횟수: {2}] ****'.format(
                qty,
                maedoHoga1, 
                maesu_count
                ) + printLog
            is_log_print_enable = True
            pass
        else:
            self.sigNoBuy.emit()

        self.shuffleConditionOccurList()

        if( is_log_print_enable ):
            util.save_log(printLog, '조건진입', folder = "log")
        pass
     
    @pyqtSlot()
    def waitingTRlimitProcessBuyStateEntered(self):
        # print(util.whoami())
        # TR 은 개당 3.7 초 제한 
        # 5연속 조회시 17초 대기 해야함 
        # print(util.whoami() )
        QTimer.singleShot(TR_TIME_LIMIT_MS,  self.sigTrWaitComplete)
        pass 

    @pyqtSlot()
    def finalStateEntered(self):
        print(util.whoami())
        self.makeJangoInfoFile()
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        util.save_log('', subject= '', folder='log')
        import subprocess
        subprocess.call(["shutdown", "-s", "-t", "500"])
        sys.exit()
        pass


    def sendorder_multi(self, rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo):
        def inner():
            self.sendOrder(rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo)
        return inner


    def printStockInfo(self, jongmokCode = 'all'):
        if( jongmokCode == 'all'):
            print(json.dumps(self.jangoInfo, ensure_ascii= False, indent =2, sort_keys = True))
        else:
            print(json.dumps(self.jangoInfo[jongmokCode], ensure_ascii= False, indent =2, sort_keys = True))
        pass
    
    def printChegyeolInfo(self, current_date = 'all'):
        if( current_date == 'all' ):
            print(json.dumps(self.chegyeolInfo, ensure_ascii= False, indent = 2, sort_keys = True))
        elif( current_date == ''):
            current_date = self.currentTime.date().strftime("%y%m%d")
            if( current_date in self.chegyeolInfo):
                print(json.dumps(self.chegyeolInfo[current_date], ensure_ascii= False, indent = 2, sort_keys = True))

    def printYupjongInfo(self):
        print(json.dumps(self.yupjongInfo, ensure_ascii= False, indent =2, sort_keys = True))

    # 주식 잔고정보 요청 
    def requestOpw00018(self, account_num):
        self.setInputValue('계좌번호', account_num)
        self.setInputValue('비밀번호', '') #  사용안함(공백)
        self.setInputValue('비빌번호입력매체구분', '00')
        self.setInputValue('조회구분', '1')

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
        
            jongmokCode = info_dict['종목번호']
            
            if( jongmokCode not in self.jangoInfo.keys() ):
                self.jangoInfo[jongmokCode] = info_dict
            else:
                # 기존에 가지고 있는 종목이면 update
                self.jangoInfo[jongmokCode].update(info_dict)

        # print(self.jangoInfo)
        return True 

    # 주식 1일봉 요청 
    def requestOpt10081(self, jongmokCode):
        # print(util.cur_time_msec() )
        datetime_str = datetime.datetime.now().strftime('%Y%m%d')
        self.setInputValue("종목코드", jongmokCode)
        self.setInputValue("기준일자", datetime_str)    
        self.setInputValue('수정주가구분', '1')
        ret = self.commRqData(jongmokCode, "opt10081", 0, kw_util.sendGibonScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString = jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True
        
    # 주식 일봉 차트 조회 
    def makeOpt10081Info(self, rQName):
        # repeatCnt = self.getRepeatCnt("opt10081", rQName)
        # jongmok_code = rQName
        # price_list = [] 

        # for i in range(repeatCnt):
        #     line = {} 
        #     for item_name in kw_util.dict_jusik['TR:일봉']:
        #         if( item_name == "종목명" ):
        #             line[item_name] = self.getMasterCodeName(rQName)
        #             continue
        #         result = self.getCommData("opt10081", rQName, i, item_name)
        #         line[item_name] = result.strip()

        #     # 일자가 맨 마지막 리스트 
        #     saved_date_str = line['일자']
        #     time_span = datetime.timedelta(days = STOP_LOSS_VALUE_DAY_RANGE) # 몇일 중  저가 계산
        #     saved_date = datetime.datetime.strptime(saved_date_str, '%Y%m%d').date()
        #     current_date = self.currentTime.date()
        #     price_list.append(int(line['저가']))
        #     if( saved_date <  current_date - time_span):
        #         break
        return True

    # 주식 분봉 tr 요청 
    def requestOpt10080(self, jongmokCode):
     # 분봉 tr 요청의 경우 너무 많은 데이터를 요청하므로 한개씩 수행 
        self.setInputValue("종목코드", jongmokCode )
        self.setInputValue("틱범위","5:5분") 
        self.setInputValue("수정주가구분","1") 
        # rQName 을 데이터로 외부에서 사용
        ret = self.commRqData(jongmokCode , "opt10080", 0, kw_util.send5minScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString =  jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True

    # 분봉 데이터 생성 
    def makeOpt10080Info(self, rQName):
        jongmok_info_dict = self.getConditionOccurList()
        if( jongmok_info_dict ):
            pass
        else:
            return False
        repeatCnt = self.getRepeatCnt("opt10080", rQName)

        total_current_price_list = []

        for i in range(min(repeatCnt, 800)):
            line = []
            for item_name in kw_util.dict_jusik['TR:분봉']:
                result = self.getCommData("opt10080", rQName, i, item_name)
                if( item_name == "현재가"):
                    total_current_price_list.append( abs(int(result)  ) )

                line.append(result.strip())
            key_value = '5분 {0}봉전'.format(i)
            jongmok_info_dict[key_value] = line
        
        for i in range(0, 200):
            fivebong_sum, twentybong_sum, sixtybong_sum, twohundred_sum = 0, 0, 0, 0

            twohundred_sum = sum(total_current_price_list[i:200+i])
            jongmok_info_dict['200봉{}평균'.format(i)] = int(twohundred_sum/ 200)

            # sixtybong_sum = sum(total_current_price_list[i:60+i])
            # jongmok_info_dict['60봉{}평균'.format(i)] = int(sixtybong_sum/ 60)

            # twentybong_sum = sum(total_current_price_list[i:20+i])
            # jongmok_info_dict['20봉{}평균'.format(i)] = int(twentybong_sum/ 20)

            # fivebong_sum = sum(total_current_price_list[i:5+i])
            # jongmok_info_dict['5봉{}평균'.format(i)] = int(fivebong_sum/ 5) 
        

        jongmok_code = jongmok_info_dict['종목코드']
        if( jongmok_code in self.jangoInfo) :
            time_cut_5min = '5분 {0}봉전'.format(TIME_CUT_MAX_DAY * 78)
            self.jangoInfo[jongmok_code]['5분봉타임컷기준'] = jongmok_info_dict[time_cut_5min]


        # RSI 14 calculate
        rsi_up_sum = 0 
        rsi_down_sum = 0
        index_current_price = kw_util.dict_jusik['TR:분봉'].index('현재가')

        for i in range(14, -1, -1):
            key_value = '5분 {0}봉전'.format(i)
            if( i != 14 ):
                key_value = '5분 {0}봉전'.format(i + 1)
                prev_fivemin_close = abs(int(jongmok_info_dict[key_value][index_current_price]))
                key_value = '5분 {0}봉전'.format(i)
                fivemin_close = abs(int(jongmok_info_dict[key_value][index_current_price]))
                if( prev_fivemin_close < fivemin_close):
                    rsi_up_sum += fivemin_close - prev_fivemin_close
                elif( prev_fivemin_close > fivemin_close):
                    rsi_down_sum += prev_fivemin_close - fivemin_close 
            pass
        
        rsi_up_avg = rsi_up_sum / 14
        rsi_down_avg = rsi_down_sum / 14
        if( rsi_up_avg !=0 and rsi_down_avg != 0 ):
            rsi_value = round(rsi_up_avg / ( rsi_up_avg + rsi_down_avg ) * 100 , 1)
        else:
            rsi_value = 100
        jongmok_info_dict['RSI14'] = str(rsi_value)
        # print(util.whoami(), self.getMasterCodeName(jongmok_code), jongmok_code,  'rsi_value: ',  rsi_value)
        return True

    # 업종 분봉 tr 요청 
    def requestOpt20005(self, yupjong_code):
        self.setInputValue("업종코드", yupjong_code )
        self.setInputValue("틱범위","5:5분") 
        self.setInputValue("수정주가구분","1") 
        ret = 0
        if( yupjong_code == '001'):
            ret = self.commRqData(yupjong_code , "opt20005", 0, kw_util.sendReqYupjongKospiScreenNo) 
        else:
            ret = self.commRqData(yupjong_code , "opt20005", 0, kw_util.sendReqYupjongKosdaqScreenNo) 
        
        errorString = None
        if( ret != 0 ):
            errorString =  yupjong_code + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True

    # 업종 분봉 데이터 생성 
    def makeOpt20005Info(self, rQName):
        if( rQName == '001'):
            yupjong_info_dict = self.yupjongInfo['코스피']
        elif( rQName == '101'):
            yupjong_info_dict = self.yupjongInfo['코스닥']
        else:
            return

        repeatCnt = self.getRepeatCnt("opt20005", rQName)

        fivebong_sum = 0
        twentybong_sum = 0 
        for i in range(min(repeatCnt, 20)):
            line = []
            for item_name in kw_util.dict_jusik['TR:업종분봉']:
                result = self.getCommData("opt20005", rQName, i, item_name)
                if( item_name == "현재가" ):
                    current_price = abs(int(result)) / 100
                    if( i < 5 ):
                        fivebong_sum += current_price
                    twentybong_sum += current_price  
                    line.append(str(current_price))
                else:
                    line.append(result.strip())
            key_value = '5분 {0}봉전'.format(i)
            yupjong_info_dict[key_value] = line
        
        yupjong_info_dict['20봉평균'] = str(round(twentybong_sum / 20, 2))
        yupjong_info_dict['5봉평균'] = str(round(fivebong_sum / 5, 2))
        return True


    # 주식 기본 정보 요청  
    def requestOpt10001(self, jongmokCode):
        # print(util.cur_time_msec() )
        self.setInputValue("종목코드", jongmokCode)
        ret = self.commRqData(jongmokCode, "opt10001", 0, kw_util.sendGibonScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString = jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True
        
    # 주식 기본 차트 조회 ( multi data 아님 )
    def makeOpt10001Info(self, rQName):
        jongmok_code = rQName
        jongmok_info_dict = self.getConditionOccurList()
        if( jongmok_info_dict ):
            pass
        else:
            return False

        for item_name in kw_util.dict_jusik['TR:기본정보']:
            result = self.getCommData("opt10001", rQName, 0, item_name)
            if( jongmok_code in self.jangoInfo ):
                self.jangoInfo[jongmok_code][item_name] = result.strip()
            jongmok_info_dict[item_name] = result.strip()
        return True

    @pyqtSlot()
    def onTimerSystemTimeout(self):
        # print(".", end='') 
        self.currentTime = datetime.datetime.now()
        if( self.getConnectState() != 1 ):
            util.save_log("Disconnected!", "시스템", folder = "log")
            self.sigDisconnected.emit() 
        else:
            if( datetime.time(*TRADING_INFO_GETTING_TIME) <=  self.currentTime.time() ): 
                self.timerSystem.stop()
                util.save_log("Stock Trade Terminate!\n\n\n\n\n", "시스템", folder = "log")
                pass
            else :
                pass
        pass

    @pyqtSlot()
    def quit(self):
        print(util.whoami())
        self.commTerminate()
        QApplication.quit()

    # 에러코드의 메시지를 출력한다.
    @pyqtSlot(int, result=str)
    def parseErrorCode(self, errCode):
        return kw_util.parseErrorCode(errCode)

    # event
    # 통신 연결 상태 변경시 이벤트
    # nErrCode가 0이면 로그인 성공, 음수면 실패
    def _OnEventConnect(self, errCode):
        print(util.whoami() + '{}'.format(errCode))
        if errCode == 0:
            self.sigConnected.emit()
        else:
            self.sigDisconnected.emit()

    # 수신 메시지 이벤트
    def _OnReceiveMsg(self, scrNo, rQName, trCode, msg):
        # print(util.whoami() + 'sScrNo: {}, sRQName: {}, sTrCode: {}, sMsg: {}'
        # .format(scrNo, rQName, trCode, msg))

        # [107066] 매수주문이 완료되었습니다.
        # [107048] 매도주문이 완료되었습니다
        # [571489] 장이 열리지않는 날입니다
        # [100000] 조회가 완료되었습니다
        printData =  'sScrNo: {}, sRQName: {}, sTrCode: {}, sMsg: {}'.format(scrNo, rQName, trCode, msg)

        # buy 하다가 오류 난경우 강제로 buy signal 생성  
        if( 'buy' in rQName and '107066' not in msg ):
            QTimer.singleShot(TR_TIME_LIMIT_MS,  self.sigBuy )

        print(printData)
        util.save_log(printData, "시스템메시지", "log")
        pass

    # Tran 수신시 이벤트
    def _OnReceiveTrData(   self, scrNo, rQName, trCode, recordName,
                            prevNext, dataLength, errorCode, message,
                            splmMsg):
        # print(util.whoami() + 'sScrNo: {}, rQName: {}, trCode: {}, prevNext {}' 
        # .format(scrNo, rQName, trCode, prevNext))

        # rQName 은 계좌번호임 
        if ( trCode == 'opw00018' ):
            if( self.makeOpw00018Info(rQName) ):
                self.sigRequestJangoComplete.emit()
            else:
                self.sigError.emit()
            pass
        elif( trCode =='opt10081'):
            if( self.makeOpt10081Info(rQName) ):
                # 잔고 정보를 뒤져서 손절가 책정이 되었는지 확인 
                # ret_vals = []
                # for jangoInfo in self.jangoInfo.values():
                #     if( '손절가' not in jangoInfo.keys() ):
                #         ret_vals.append(False)
                # if( ret_vals.count(False) == 0 ):
                #     self.printStockInfo()
                #     self.sigCalculateStoplossComplete.emit()
                pass
            else:
                self.sigError.emit()

        #주식 기본 정보 요청 rQName 은 개별 종목 코드임
        elif( trCode == "opt10001"):
            if( self.makeOpt10001Info(rQName) ):
                self.sigGetEtcInfo.emit()
            else:
                self.sigError.emit()
            pass

        # 주식 분봉 정보 요청 rQName 개별 종목 코드  
        elif( trCode == "opt10080"):     
            if( self.makeOpt10080Info(rQName) ) :
                self.sigGet5minInfo.emit()
            else:
                self.sigError.emit()
            pass

        # 업종 분봉 rQName 업종 코드  
        elif( trCode == "opt20005"):     
            if( self.makeOpt20005Info(rQName) ) :
                self.sigGetEtcInfo.emit()
            else:
                self.sigError.emit()
            pass

    # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmokCode, realType, realData):
        # print(util.whoami() + 'jongmokCode: {}, {}, realType: {}'
        #         .format(jongmokCode, self.getMasterCodeName(jongmokCode),  realType))

        # 장전에도 주식 호가 잔량 값이 올수 있으므로 유의해야함 
        if( realType == "주식호가잔량"):
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))

            self.makeHogaJanRyangInfo(jongmokCode)                

        #주식 체결로는 사고 팔기에는 반응이 너무 느림 
        elif( realType == "주식체결"):
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))
            self.makeBasicInfo(jongmokCode)

            # WARNING: 장중에 급등으로 거래 정지 되어 동시 호가진행되는 경우에 대비하여 체결가 정보 발생했을때만 stoploss 진행함. 
            self.processStopLoss(jongmokCode)
            pass
        
        elif( realType == "주식시세"):
            # 장종료 후에 나옴 
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))
            pass
        
        elif( realType == "업종지수" ):
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))
            result = '' 
            for col_name in kw_util.dict_jusik['실시간-업종지수']:
                result = self.getCommRealData(jongmokCode, kw_util.name_fid[col_name] ) 
                if( jongmokCode == '001'):
                    self.yupjongInfo['코스피'][col_name] = result.strip()
                elif( jongmokCode == '100'):
                    self.yupjongInfo['코스닥'][col_name] = result.strip()
            pass 
        
        elif( realType == '장시작시간'):
            # TODO: 장시작 30분전부터 실시간 정보가 올라오는데 이를 토대로 가변적으로 장시작시간을 가늠할수 있도록 기능 추가 필요 
            # 장운영구분(0:장시작전, 2:장종료전, 3:장시작, 4,8:장종료, 9:장마감)
            # 동시호가 시간에 매수 주문 
            result = self.getCommRealData(realType, kw_util.name_fid['장운영구분'] ) 
            if( result == '2'):
                self.sigTerminating.emit()
            elif( result == '4' ): # 장종료 후 5분뒤에 프로그램 종료 하게 함  
                QTimer.singleShot(300000, self.sigStockComplete)

            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))
        
            print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
                .format(jongmokCode, realType, realData))
            pass

    def calculateSuik(self, jongmok_code, current_price):
        current_jango = self.jangoInfo[jongmok_code]
        maeip_price = abs(int(current_jango['매입가']))
        boyou_suryang = int(current_jango['보유수량'])

        suik_price = round( (current_price - maeip_price) * boyou_suryang , 2)
        current_jango['수익'] = suik_price 
        current_jango['수익율'] = round( ( (current_price-maeip_price)  / maeip_price ) * 100 , 2) 
        pass

    # 실시간 호가 잔량 정보         
    def makeHogaJanRyangInfo(self, jongmokCode):
        #주식 호가 잔량 정보 요청 
        result = None 
        for col_name in kw_util.dict_jusik['실시간-주식호가잔량']:
            result = self.getCommRealData(jongmokCode, kw_util.name_fid[col_name] ) 

            if( jongmokCode in self.jangoInfo ):
                self.jangoInfo[jongmokCode][col_name] = result.strip()
            if( jongmokCode in self.getCodeListConditionOccurList() ):
                self.setHogaConditionOccurList(jongmokCode, col_name, result.strip() )
        pass 

    # 실시간 체결(기본) 정보         
    def makeBasicInfo(self, jongmokCode):
        #주식 호가 잔량 정보 요청 
        result = None 
        for col_name in kw_util.dict_jusik['실시간-주식체결']:
            result = self.getCommRealData(jongmokCode, kw_util.name_fid[col_name] ) 

            if( jongmokCode in self.jangoInfo ):
                self.jangoInfo[jongmokCode][col_name] = result.strip()
            if( jongmokCode in self.getCodeListConditionOccurList() ):
                self.setHogaConditionOccurList(jongmokCode, col_name, result.strip() )
        pass 

    def processStopLoss(self, jongmokCode):
        jongmokName = self.getMasterCodeName(jongmokCode)
        if( self.isTradeAvailable() == False ):
            return
        
        # 예외 처리 리스트이면 종료 
        if( jongmokCode in EXCEPTION_LIST ):
            return

        # 잔고에 없는 종목이면 종료 
        if( jongmokCode not in self.jangoInfo ):
            return 
        current_jango = self.jangoInfo[jongmokCode]

        if( '손절가' not in current_jango or '매수호가1' not in current_jango or '매매가능수량' not in current_jango  ):
            return

        jangosuryang = int( current_jango['매매가능수량'] )
        stop_loss = 0
        ########################################################################################
        # 업종 이평가를 기준으로 stop loss 값 조정 
        # twenty_avr = 0
        # five_avr = 0
        # if( '20봉평균' in self.yupjongInfo['코스피'] and
        #     '5봉평균' in self.yupjongInfo['코스피'] and 
        #     '20봉평균' in self.yupjongInfo['코스닥'] and
        #     '5봉평균' in self.yupjongInfo['코스닥']  
        # ):
        #     if( jongmokCode in self.kospiCodeList):
        #         twenty_avr = abs(float(self.yupjongInfo['코스피']['20봉평균']))
        #         five_avr = abs(float(self.yupjongInfo['코스피']['5봉평균']))
        #     else:
        #         twenty_avr = abs(float(self.yupjongInfo['코스닥']['20봉평균']))
        #         five_avr = abs(float(self.yupjongInfo['코스닥']['5봉평균']))

        #     stop_loss = int(current_jango['손절가']) 
        # else:
        #     stop_loss = int(current_jango['손절가'])
        stop_loss = int(current_jango['손절가'])
        stop_plus = int(current_jango['이익실현가'])
        maeipga = int(current_jango['매입가'])


        # 호가 정보는 문자열로 기준가 대비 + , - 값이 붙어 나옴 
        maesuHoga1 =  abs(int(current_jango['매수호가1']))
        maesuHogaAmount1 =  int(current_jango['매수호가수량1'])
        maesuHoga2 =  abs(int(current_jango['매수호가2']))
        maesuHogaAmount2 =  int(current_jango['매수호가수량2'])
        #    print( util.whoami() +  maeuoga1 + " " + maesuHogaAmount1 + " " + maesuHoga2 + " " + maesuHogaAmount2 )
        totalAmount =  maesuHoga1 * maesuHogaAmount1 + maesuHoga2 * maesuHogaAmount2
        # print( util.whoami() + jongmokName + " " + str(sum))

        isSell = False
        printData = jongmokCode + ' {0:20} '.format(jongmokName) 

        ########################################################################################
        # time cut 적용 
        base_time_str = ''
        last_chegyeol_time_str = ''
        # if( '5분봉타임컷기준' in current_jango ):
        #     base_time_str =  current_jango['5분봉타임컷기준'][2]
        #     base_time = datetime.datetime.strptime(base_time_str, '%Y%m%d%H%M%S')
        #     last_chegyeol_time_str = current_jango['주문/체결시간'][-1]
        #     maeip_time = datetime.datetime.strptime(last_chegyeol_time_str, '%Y%m%d%H%M%S')

        #     if( maeip_time < base_time ):
        #         stop_loss = 99999999 

        #########################################################################################
        # day trading 용 
        if( DAY_TRADING_ENABLE == True ):
            # day trading 주식 거래 시간 종료가 가까운 경우 모든 종목 매도 
            time_span = datetime.timedelta(minutes = 10 )
            dst_time = datetime.datetime.combine(datetime.date.today(), datetime.time(*DAY_TRADING_END_TIME)) + time_span

            current_time = datetime.datetime.now()
            if( datetime.time(*DAY_TRADING_END_TIME) <  current_time.time() and dst_time > current_time ):
                # 0 으로 넣고 로그 남기면서 매도 처리하게 함  
                stop_loss = 0  
                pass

        # 손절 / 익절 계산 
        # 정리나, 손절의 경우 시장가로 팔고 익절의 경우 보통가로 팜 
        isSijanga = False
        maedo_type = ''
        if( stop_loss == 0 ):
            maedo_type = "(당일정리)"
            printData += maedo_type 
            isSijanga = True
            isSell = True
        elif( stop_loss == 99999999 ):
            maedo_type = "(타임컷임)"
            printData += maedo_type 
            isSijanga = True
            isSell = True
        elif( stop_loss >= maesuHoga1 ) :
            maedo_type = "(손절이다)"
            printData += maedo_type 
            isSijanga = True
            isSell = True
        elif( stop_plus < maesuHoga1 ) :
            if( totalAmount >= TOTAL_BUY_AMOUNT):
                maedo_type = "(익절이다)"
                printData += maedo_type 
                isSell = True 
            else:
                maedo_type = "(익절미달)"
                printData += maedo_type 
                isSell = True

        printData +=    ' 손절가: {0:7}/'.format(str(stop_loss)) + \
                        ' 이익실현가: {0:7}/'.format(str(stop_plus)) + \
                        ' 매입가: {0:7}/'.format(str(maeipga)) + \
                        ' 잔고수량: {0:7}'.format(str(jangosuryang)) +\
                        ' 타임컷 기준 시간: {0:7}'.format(base_time_str) + \
                        ' 최근 주문/체결시간: {0:7}'.format(last_chegyeol_time_str) + \
                        ' 매수호가1 {0:7}/'.format(str(maesuHoga1)) + \
                        ' 매수호가수량1 {0:7}/'.format(str(maesuHogaAmount1)) + \
                        ' 매수호가2 {0:7}/'.format(str(maesuHoga2)) + \
                        ' 매수호가수량2 {0:7}/'.format(str(maesuHogaAmount2)) 

        if( isSell == True ):
            # processStop 의 경우 체결될때마다 호출되므로 중복 주문이 나가지 않게 함 
            if( '매도중' not in current_jango):
                current_jango['매도중'] = maedo_type
                if( isSijanga == True ):
                    result = self.sendOrder("sell_"  + jongmokCode, kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
                                        jongmokCode, jangosuryang, 0 , kw_util.dict_order["시장가"], "")
                else:
                    result = self.sendOrder("sell_"  + jongmokCode, kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
                                        jongmokCode, jangosuryang, maesuHoga1 , kw_util.dict_order["지정가"], "")

                util.save_log(printData, '매도', 'log')
                print("S " + jongmokCode + ' ' + str(result), sep= "")
            pass
        pass

    # 체결데이터를 받은 시점을 알려준다.
    # sGubun – 0:주문체결통보, 1:잔고통보, 3:특이신호
    # sFidList – 데이터 구분은 ‘;’ 이다.
    '''
    _OnReceiveChejanData gubun: 1, itemCnt: 27, fidList: 9201;9001;917;916;302;10;930;931;932;933;945;946;950;951;27;28;307;8019;957;958;918;990;991;992;993;959;924
    {'종목코드': 'A010050', '당일실현손익률(유가)': '0.00', '대출일': '00000000', '당일실현손익률(신용)': '0.00', '(최우선)매수호가': '+805', '당일순매수수량': '5', '총매입가': '4043', 
    '당일총매도손일': '0', '만기일': '00000000', '신용금액': '0', '당일실현손익(신용)': '0', '현재가': '+806', '기준가': '802', '계좌번호': ', '보유수량': '5', 
    '예수금': '0', '주문가능수량': '5', '종목명': '우리종금                                ', '손익율': '0.00', '당일실현손익(유가)': '0', '담보대출수량': '0', '924': '0', 
    '매입단가': '809', '신용구분': '00', '매도/매수구분': '2', '(최우선)매도호가': '+806', '신용이자': '0'}
    ''' 
    def _OnReceiveChejanData(self, gubun, itemCnt, fidList):
        # print(util.whoami() + 'gubun: {}, itemCnt: {}, fidList: {}'
        #         .format(gubun, itemCnt, fidList))
        if( gubun == "1"): # 잔고 정보
            # 잔고 정보에서는 매도/매수 구분이 되지 않음 

            jongmok_code = self.getChejanData(kw_util.name_fid['종목코드'])[1:]
            boyou_suryang = int(self.getChejanData(kw_util.name_fid['보유수량']))
            jumun_ganeung_suryang = int(self.getChejanData(kw_util.name_fid['주문가능수량']))
            maeip_danga = int(self.getChejanData(kw_util.name_fid['매입단가']))
            jongmok_name= self.getChejanData(kw_util.name_fid['종목명']).strip()
            current_price = abs(int(self.getChejanData(kw_util.name_fid['현재가'])))

            #미체결 수량이 있는 경우 잔고 정보 저장하지 않도록 함 
            if( jongmok_code in self.michegyeolInfo):
                if( self.michegyeolInfo[jongmok_code]['미체결수량'] ):
                    return 
            # 미체결 수량이 없으므로 정보 삭제 
            del ( self.michegyeolInfo[jongmok_code] )
            if( boyou_suryang == 0 ):
                # 보유 수량이 0 인 경우 매도 수행 
                if( jongmok_code not in self.todayTradedCodeList):
                    self.todayTradedCodeList.append(jongmok_code)
                self.jangoInfo.pop(jongmok_code)
                self.removeConditionOccurList(jongmok_code)
            else:
                # 보유 수량이 늘었다는 것은 매수수행했다는 소리임 
                self.sigBuy.emit() 

                # 아래 잔고 정보의 경우 TR:계좌평가잔고내역요청 필드와 일치하게 만들어야 함 
                current_jango = {}
                current_jango['보유수량'] = boyou_suryang
                current_jango['매매가능수량'] =  jumun_ganeung_suryang # TR 잔고에서 매매가능 수량 이란 이름으로 사용되므로 
                current_jango['매입가'] = maeip_danga
                current_jango['종목번호'] = jongmok_code
                current_jango['종목명'] = jongmok_name.strip()
                chegyeol_info = util.cur_date_time('%Y%m%d%H%M%S') + ":" + str(current_price)

                if( jongmok_code not in self.jangoInfo):
                    current_jango['주문/체결시간'] = [util.cur_date_time('%Y%m%d%H%M%S')] 
                    current_jango['체결가/체결시간'] = [chegyeol_info] 
                    current_jango['최근매수가'] = [current_price]
                    current_jango['매수횟수'] = 1 

                    self.jangoInfo[jongmok_code] = current_jango 

                else:
                    chegyeol_time_list = self.jangoInfo[jongmok_code]['주문/체결시간']  
                    chegyeol_time_list.append( util.cur_date_time('%Y%m%d%H%M%S'))
                    current_jango['주문/체결시간'] = chegyeol_time_list

                    last_chegyeol_info = self.jangoInfo[jongmok_code]['체결가/체결시간'][-1]
                    if( int(last_chegyeol_info.split(':')[1]) != current_price ):
                        chegyeol_info_list = self.jangoInfo[jongmok_code]['체결가/체결시간']  
                        chegyeol_info_list.append( chegyeol_info )
                        current_jango['체결가/체결시간'] = chegyeol_info_list

                    price_list = self.jangoInfo[jongmok_code]['최근매수가']
                    last_price = price_list[-1] 
                    if( last_price != current_price):
                        #매수가 나눠져서 진행 중이므로 자료 매수횟수 업데이트 안함 
                        price_list.append( current_price )
                    current_jango['최근매수가'] = price_list

                    chumae_count = self.jangoInfo[jongmok_code]['매수횟수']
                    if( last_price != current_price):
                        current_jango['매수횟수'] = chumae_count + 1
                    else:
                        current_jango['매수횟수'] = chumae_count

                    self.jangoInfo[jongmok_code].update(current_jango)


            self.makeEtcJangoInfo(jongmok_code)
            self.makeJangoInfoFile()
            pass

        elif ( gubun == "0"):
            jumun_sangtae =  self.getChejanData(kw_util.name_fid['주문상태'])
            jongmok_code = self.getChejanData(kw_util.name_fid['종목코드'])[1:]
            michegyeol_suryang = int(self.getChejanData(kw_util.name_fid['미체결수량']))
            # 주문 상태 
            # 매수 시 접수(gubun-0) - 체결(gubun-0) - 잔고(gubun-1)     
            # 매도 시 접수(gubun-0) - 잔고(gubun-1) - 체결(gubun-0) - 잔고(gubun-1)   순임 
            # 미체결 수량 정보를 입력하여 잔고 정보 처리시 미체결 수량 있는 경우에 대한 처리를 하도록 함 
            if( jongmok_code not in self.michegyeolInfo):
                self.michegyeolInfo[jongmok_code] = {}
            self.michegyeolInfo[jongmok_code]['미체결수량'] = michegyeol_suryang

            if( jumun_sangtae == "체결"):
                self.makeChegyeolInfo(jongmok_code, fidList)
                self.makeChegyeolInfoFile()
                pass
            
            pass


    def makeChegyeolInfoFile(self):
        # print(util.whoami())
        with open(CHEGYEOL_INFO_FILE_PATH, 'w', encoding = 'utf8' ) as f:
            f.write(json.dumps(self.chegyeolInfo, ensure_ascii= False, indent= 2, sort_keys = True ))
        pass

    # 첫 잔고 정보 요청시 호출됨 
    # 매수, 매도후 체결 정보로 잔고 정보 올때 호출됨 
    def makeEtcJangoInfo(self, jongmok_code, priority = 'server'): 

        if( jongmok_code not in self.jangoInfo ):
            return
        current_jango = {}

        if( priority == 'server' ):
            current_jango = self.jangoInfo[jongmok_code]
            maeip_price = current_jango['매입가']

            if( '매수횟수' not in current_jango ):
                if( jongmok_code in self.jangoInfoFromFile):
                    current_jango['매수횟수'] = self.jangoInfoFromFile[jongmok_code].get('매수횟수', 1)
                else:
                    current_jango['매수횟수']  = 1
                    pass

            maesu_count = current_jango['매수횟수']
            # 손절가 다시 계산 
            stop_loss_value = STOP_LOSS_PER_MAESU_COUNT[maesu_count -1]
            stop_plus_value = STOP_PLUS_PER_MAESU_COUNT[maesu_count -1]

            current_jango['손절가'] =     round( maeip_price *  (1 - (stop_loss_value - SLIPPAGE) / 100) , 2 )
            current_jango['이익실현가'] = round( maeip_price *  (1 + (stop_plus_value + SLIPPAGE) / 100) , 2 )

            if( '주문/체결시간' not in current_jango ):
                if( jongmok_code in self.jangoInfoFromFile):
                    current_jango['주문/체결시간'] = self.jangoInfoFromFile[jongmok_code].get('주문/체결시간', [])
                else:
                    current_jango['주문/체결시간'] = []      

            if( '체결가/체결시간' not in current_jango ):
                if( jongmok_code in self.jangoInfoFromFile):
                    current_jango['체결가/체결시간'] = self.jangoInfoFromFile[jongmok_code].get('체결가/체결시간', [])
                else:
                    current_jango['체결가/체결시간'] = []      

            if( '최근매수가' not in current_jango ):
                if( jongmok_code in self.jangoInfoFromFile):
                    current_jango['최근매수가'] = self.jangoInfoFromFile[jongmok_code].get('최근매수가', [])
                else:
                    current_jango['최근매수가'] =  []      
        else:

            if( jongmok_code in self.jangoInfoFromFile ):
                current_jango = self.jangoInfoFromFile[jongmok_code]
            else:
                current_jango = self.jangoInfo[jongmok_code]

        self.jangoInfo[jongmok_code].update(current_jango)
        pass

    @pyqtSlot()
    def makeJangoInfoFile(self):
        print(util.whoami())
        remove_keys = [ '매도호가1','매도호가2', '매도호가수량1', '매도호가수량2', '매도호가총잔량',
                        '매수호가1', '매수호가2', '매수호가수량1', '매수호가수량2', '매수호가수량3', '매수호가수량4', '매수호가총잔량',
                        '현재가', '호가시간', '세금', '전일종가', '현재가', '종목번호', '수익율', '수익', '잔고' , '매도중', '시가', '고가', '저가', '장구분', 
                        '거래량', '등락율', '전일대비', '기준가', '상한가', '하한가', '5분봉타임컷기준' ]
        temp = copy.deepcopy(self.jangoInfo)
        # 불필요 필드 제거 
        for jongmok_code, contents in temp.items():
            for key in remove_keys:
                if( key in contents):
                    del contents[key]

        with open(JANGO_INFO_FILE_PATH, 'w', encoding = 'utf8' ) as f:
            f.write(json.dumps(temp, ensure_ascii= False, indent= 2, sort_keys = True ))
        pass

    def makeChegyeolInfo(self, jongmok_code, fidList):
        fids = fidList.split(";")
        printData = "" 
        info = [] 

        # 미체결 수량이 0 이 아닌 경우 다시 체결 정보가 올라 오므로 0인경우 처리 안함 
        michegyeol_suryung = int(self.getChejanData(kw_util.name_fid['미체결수량']).strip())
        if( michegyeol_suryung != 0 ):
            return
        nFid = kw_util.name_fid['매도매수구분']
        # 1, 2 컬럼의 수익과 수익율 필드 채움 
        if( str(nFid) in fids):
            result = self.getChejanData(nFid).strip()
            # 첫 매수시는 잔고 정보가 없을 수 있으므로 
            current_jango = self.jangoInfo.get(jongmok_code, {})
            if( int(result) == 1): #매도
                # 체결가를 통해 수익율 필드 업데이트 
                current_price = int(self.getChejanData(kw_util.name_fid['체결가']).strip())
                self.calculateSuik(jongmok_code, current_price)

                # 매도시 체결정보는 수익율 필드가 존재 
                profit = current_jango.get('수익', '0')
                profit_percent = current_jango.get('수익율', '0' )
                chumae_count = int(current_jango.get('매수횟수', '0'))
                maedo_type = current_jango.get('매도중', '0')
                if( maedo_type == ''):
                    maedo_type = '수동매도'
                info.append('{0:>10}'.format(profit_percent))
                info.append('{0:>10}'.format(profit))
                info.append(' 매수횟수: {0:>1} '.format(chumae_count))
                info.append(' {0} '.format(maedo_type))
                pass
            else: #매수 
                # 매수시 체결정보는 수익율 / 수익 필드가  
                info.append('{0:>10}'.format('0'))
                info.append('{0:>10}'.format('0'))
                # 체결시는 매수 횟수 정보가 업데이트 되지 않았기 때문에 +1 해줌  
                chumae_count = int(current_jango.get('매수횟수', '0'))
                info.append(' 매수횟수: {0:>1} '.format(chumae_count + 1))
                info.append(' {0} '.format('(단순매수)'))



        for col_name in kw_util.dict_jusik["체결정보"]:
            nFid = None
            result = ""
            if( col_name not in kw_util.name_fid ):
                continue

            nFid = kw_util.name_fid[col_name]

            if( str(nFid) in fids):
                result = self.getChejanData(nFid).strip()
                if( col_name == '종목코드'):
                    result = result[1:] 
                if( col_name == '체결가' ):
                    result = '{0:>10}'.format(result)
                
                if( col_name == '체결량' or col_name == '미체결수량'):
                    result = '{0:>7}'.format(result)

                info.append(' {} '.format(result))
                printData += col_name + ": " + result + ", " 
    
        current_date = self.currentTime.date().strftime('%y%m%d')

        if( current_date not in self.chegyeolInfo) :
            self.chegyeolInfo[current_date] = [] 

        self.chegyeolInfo[current_date].append('|'.join(info))
        util.save_log(printData, "*체결정보", folder= "log")
        pass

    # 로컬에 사용자조건식 저장 성공여부 응답 이벤트
    # 0:(실패) 1:(성공)
    def _OnReceiveConditionVer(self, ret, msg):
        print(util.whoami() + 'ret: {}, msg: {}'
            .format(ret, msg))
        if ret == 1:
            self.sigGetConditionCplt.emit()

    # 조건검색 조회응답으로 종목리스트를 구분자(“;”)로 붙어서 받는 시점.
    # LPCTSTR sScrNo : 종목코드
    # LPCTSTR strCodeList : 종목리스트(“;”로 구분)
    # LPCTSTR strConditionName : 조건명
    # int nIndex : 조건명 인덱스
    # int nNext : 연속조회(2:연속조회, 0:연속조회없음)
    def _OnReceiveTrCondition(self, scrNo, codeList, conditionName, index, next):
        # print(util.whoami() + 'scrNo: {}, codeList: {}, conditionName: {} '
        # 'index: {}, next: {}'
        # .format(scrNo, codeList, conditionName, index, next ))
        codes = codeList.split(';')[:-1]
        # 마지막 split 결과 None 이므로 삭제 
        for code in codes:
            print('condition occur list add code: {} '.format(code) + self.getMasterCodeName(code))
            self.addConditionOccurList(code)

    # 편입, 이탈 종목이 실시간으로 들어옵니다.
    # strCode : 종목코드
    # strType : 편입(“I”), 이탈(“D”)
    # strConditionName : 조건명
    # strConditionIndex : 조건명 인덱스
    def _OnReceiveRealCondition(self, code, type, conditionName, conditionIndex):
        print(util.whoami() + 'code: {}, type: {}, conditionName: {}, conditionIndex: {}'
        .format(code, type, conditionName, conditionIndex ))
        if type == 'I':
            self.addConditionOccurList(code) # 조건 발생한 경우 해당 내용 list 에 추가  
        else:
            self.conditionRevemoList.append(code)
            pass

    def addConditionOccurList(self, jongmok_code):
        #발생시간, 종목코드,  종목명
        jongmok_name = self.getMasterCodeName(jongmok_code)
        ret_vals = []

        # 중복 제거 
        for item_dict in self.conditionOccurList:
            if( jongmok_code == item_dict['종목코드'] ):
                ret_vals.append(True)
            
        if( ret_vals.count(True) ):
            pass
        else:
            self.conditionOccurList.append( {'종목명': jongmok_name, '종목코드': jongmok_code} )
            self.sigConditionOccur.emit()
        pass
    
    def removeConditionOccurList(self, jongmok_code):
        for item_dict in self.conditionOccurList:
            if( item_dict['종목코드'] == jongmok_code ):
                self.conditionOccurList.remove(item_dict)
                break
        pass

    def getConditionOccurList(self):
        if( len(self.conditionOccurList ) ):
            return self.conditionOccurList[0]
        else:
            return None
        pass
    
    def getCodeListConditionOccurList(self):
        items = []
        for item_dict in self.conditionOccurList:
            items.append(item_dict['종목코드'])
        return items
    
    def setHogaConditionOccurList(self, jongmok_code, col_name, value):
        for index, item_dict in enumerate(self.conditionOccurList):
            if( item_dict['종목코드'] == jongmok_code ):
                item_dict[col_name] = value

        
    # 다음 codition list 를 감시 하기 위해 종목 섞기 
    def shuffleConditionOccurList(self):
        jongmok_info_dict = self.getConditionOccurList()
        jongmok_code = jongmok_info_dict['종목코드']
        self.removeConditionOccurList(jongmok_code)
        self.conditionOccurList.append(jongmok_info_dict)

     # 실시간  주식 정보 요청 요청리스트 갱신  
     # WARNING: 실시간 요청도 TR 처럼 초당 횟수 제한이 있으므로 잘 사용해야함 
    def refreshRealRequest(self):
        # 버그로 모두 지우고 새로 등록하게 함 
        # print(util.whoami() )
        self.setRealRemove("ALL", "ALL")
        codeList  = []

        for code in self.jangoInfo.keys():
            if( code not in codeList):
                codeList.append(code)

        condition_list = self.getCodeListConditionOccurList()
        for code in condition_list: 
            if( code not in codeList):
                codeList.append(code)

        if( len(codeList) == 0 ):
            # 종목 미보유로 실시간 체결 요청 할게 없는 경우 코스닥 코스피 실시간 체결가가 올라오지 않으므로 임시로 하나 등록  
            codeList.append('044180')
        else:
            for code in codeList:
                if ( code not in EXCEPTION_LIST):
                    self.addConditionOccurList(code)

        # 실시간 호가 정보 요청 "0" 은 이전거 제외 하고 새로 요청
        if( len(codeList) ):
           #  WARNING: 주식 시세 실시간은 리턴되지 않음!
           #    tmp = self.setRealReg(kw_util.sendRealRegSiseSrcNo, ';'.join(codeList), kw_util.type_fidset['주식시세'], "0")
           tmp = self.setRealReg(kw_util.sendRealRegHogaScrNo, ';'.join(codeList), kw_util.type_fidset['주식호가잔량'], "0")
           tmp = self.setRealReg(kw_util.sendRealRegChegyeolScrNo, ';'.join(codeList), kw_util.type_fidset['주식체결'], "0")
           tmp = self.setRealReg(kw_util.sendRealRegUpjongScrNo, '001;101', kw_util.type_fidset['업종지수'], "0")

    def make_excel(self, file_path, data_dict):
        result = False
        result = os.path.isfile(file_path)
        if( result ) :
            # excel open 
            wb = xw.Book(file_path)
            sheet_names = [sheet.name for sheet in wb.sheets]
            insert_sheet_names = []
            # print(sheet_names)
            for key, value in data_dict.items():
                # sheet name 이 존재 안하면 sheet add
                sheet_name = key[0:4]
                if( sheet_name not in sheet_names ):
                    if( sheet_name not in insert_sheet_names ):
                        insert_sheet_names.append(sheet_name)

            for insert_sheet in insert_sheet_names:
                wb.sheets.add(name = insert_sheet)
            # sheet name 은 YYMM 형식 
            sheet_names = [sheet.name for sheet in wb.sheets]
            all_items = []

            for sheet_name in sheet_names:
                # key 값이 match 되는것을 찾음 
                for sorted_key in sorted(data_dict):
                    input_data_sheet_name = sorted_key[0:4]
                    if( input_data_sheet_name == sheet_name ):
                        all_items.append( [sorted_key, '', '', '', '', '', '', '','', '', '-' * 128] )
                        for line in data_dict[sorted_key]:
                            items = [ item.strip() for item in line.split('|') ]
                            items.insert(0, '')
                            all_items.append(items)

                wb.sheets[sheet_name].activate()
                xw.Range('A1').value = all_items
                all_items.clear()

            # save
            wb.save()
            wb.app.quit()

    # method 
    # 로그인
    # 0 - 성공, 음수값은 실패
    # 단순 API 호출이 되었느냐 안되었느냐만 확인 가능 
    @pyqtSlot(result=int)
    def commConnect(self):
        return self.ocx.dynamicCall("CommConnect()")

    # 로그인 상태 확인
    # 0:미연결, 1:연결완료, 그외는 에러
    @pyqtSlot(result=int)
    def getConnectState(self):
        return self.ocx.dynamicCall("GetConnectState()")

    # 로그 아웃
    @pyqtSlot()
    def commTerminate(self):
        self.ocx.dynamicCall("CommTerminate()")

    # 로그인한 사용자 정보를 반환한다.
    # “ACCOUNT_CNT” – 전체 계좌 개수를 반환한다.
    # "ACCNO" – 전체 계좌를 반환한다. 계좌별 구분은 ‘;’이다.
    # “USER_ID” - 사용자 ID를 반환한다.
    # “USER_NAME” – 사용자명을 반환한다.
    # “KEY_BSECGB” – 키보드보안 해지여부. 0:정상, 1:해지
    # “FIREW_SECGB” – 방화벽 설정 여부. 0:미설정, 1:설정, 2:해지
    @pyqtSlot(str, result=str)
    def getLoginInfo(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", [tag])

    # Tran 입력 값을 서버통신 전에 입력값일 저장한다.
    @pyqtSlot(str, str)
    def setInputValue(self, id, value):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", id, value)


    @pyqtSlot(str, result=str)
    def getCodeListByMarket(self, sMarket):
        return self.ocx.dynamicCall("GetCodeListByMarket(QString)", sMarket)

    # 통신 데이터를 송신한다.
    # 0이면 정상
    # OP_ERR_SISE_OVERFLOW – 과도한 시세조회로 인한 통신불가
    # OP_ERR_RQ_STRUCT_FAIL – 입력 구조체 생성 실패
    # OP_ERR_RQ_STRING_FAIL – 요청전문 작성 실패
    # OP_ERR_NONE – 정상처리
    @pyqtSlot(str, str, int, str, result=int)
    def commRqData(self, rQName, trCode, prevNext, screenNo):
        return self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rQName, trCode, prevNext, screenNo)

    # 수신 받은 데이터의 반복 개수를 반환한다.
    @pyqtSlot(str, str, result=int)
    def getRepeatCnt(self, trCode, recordName):
        return self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trCode, recordName)

    # Tran 데이터, 실시간 데이터, 체결잔고 데이터를 반환한다.
    # 1. Tran 데이터
    # 2. 실시간 데이터
    # 3. 체결 데이터
    # 1. Tran 데이터
    # sJongmokCode : Tran명
    # sRealType : 사용안함
    # sFieldName : 레코드명
    # nIndex : 반복인덱스
    # sInnerFieldName: 아이템명
    # 2. 실시간 데이터
    # sJongmokCode : Key Code
    # sRealType : Real Type
    # sFieldName : Item Index (FID)
    # nIndex : 사용안함
    # sInnerFieldName:사용안함
    # 3. 체결 데이터
    # sJongmokCode : 체결구분
    # sRealType : “-1”
    # sFieldName : 사용안함
    # nIndex : ItemIndex
    # sInnerFieldName:사용안함
    @pyqtSlot(str, str, str, int, str, result=str)
    def commGetData(self, jongmokCode, realType, fieldName, index, innerFieldName):
        return self.ocx.dynamicCall("CommGetData(QString, QString, QString, int, QString)", jongmokCode, realType, fieldName, index, innerFieldName).strip()

    # strRealType – 실시간 구분
    # nFid – 실시간 아이템
    # Ex) 현재가출력 - openApi.GetCommRealData(“주식시세”, 10);
    # 참고)실시간 현재가는 주식시세, 주식체결 등 다른 실시간타입(RealType)으로도 수신가능
    @pyqtSlot(str, int, result=str)
    def getCommRealData(self, realType, fid):
        return self.ocx.dynamicCall("GetCommRealData(QString, int)", realType, fid).strip()

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
    @pyqtSlot(str, str, str, int, str, int, int, str, str, result=int)
    def sendOrder(self, rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo):
        return self.ocx.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)", [rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo])

    # 체결잔고 데이터를 반환한다.
    @pyqtSlot(int, result=str)
    def getChejanData(self, fid):
        return self.ocx.dynamicCall("GetChejanData(int)", fid)

    # 서버에 저장된 사용자 조건식을 가져온다.
    @pyqtSlot(result=int)
    def getConditionLoad(self):
        return self.ocx.dynamicCall("GetConditionLoad()")

    # 조건검색 조건명 리스트를 받아온다.
    # 조건명 리스트(인덱스^조건명)
    # 조건명 리스트를 구분(“;”)하여 받아온다
    @pyqtSlot(result=str)
    def getConditionNameList(self):
        return self.ocx.dynamicCall("GetConditionNameList()")

    # 조건검색 종목조회TR송신한다.
    # LPCTSTR strScrNo : 화면번호
    # LPCTSTR strConditionName : 조건명
    # int nIndex : 조건명인덱스
    # int nSearch : 조회구분(0:일반조회, 1:실시간조회, 2:연속조회)
    # 1:실시간조회의 화면 개수의 최대는 10개
    @pyqtSlot(str, str, int, int)
    def sendCondition(self, scrNo, conditionName, index, search):
        self.ocx.dynamicCall("SendCondition(QString,QString, int, int)", scrNo, conditionName, index, search)

    # 실시간 조건검색을 중지합니다.
    # ※ 화면당 실시간 조건검색은 최대 10개로 제한되어 있어서 더 이상 실시간 조건검색을 원하지 않는 조건은 중지해야만 카운트 되지 않습니다.
    @pyqtSlot(str, str, int)
    def sendConditionStop(self, scrNo, conditionName, index):
        self.ocx.dynamicCall("SendConditionStop(QString, QString, int)", scrNo, conditionName, index)

    # 복수종목조회 Tran을 서버로 송신한다.
    # OP_ERR_RQ_STRING – 요청 전문 작성 실패
    # OP_ERR_NONE - 정상처리
    #
    # sArrCode – 종목간 구분은 ‘;’이다.
    # nTypeFlag – 0:주식관심종목정보, 3:선물옵션관심종목정보
    @pyqtSlot(str, bool, int, int, str, str)
    def commKwRqData(self, arrCode, next, codeCount, typeFlag, rQName, screenNo):
    	self.ocx.dynamicCall("CommKwRqData(QString, QBoolean, int, int, QString, QString)", arrCode, next, codeCount, typeFlag, rQName, screenNo)

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
    @pyqtSlot(str, str, str, str,  result=int)
    def setRealReg(self, screenNo, codeList, fidList, optType):
        return self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screenNo, codeList, fidList, optType)

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
    @pyqtSlot(str, str)
    def setRealRemove(self, scrNo, delCode):
        self.ocx.dynamicCall("SetRealRemove(QString, QString)", scrNo, delCode)
        
        
    # 수신 데이터를 반환한다. 
    # LPCTSTR strTrCode : 조회한TR코드
    # LPCTSTR strRecordName: 조회한 TR명
    # nIndex : 복수 데이터 인덱스
    # strItemName: 아이템 명
    # 반환값: 수신 데이터
    
    @pyqtSlot(str, str, int, str, result=str)
    def getCommData(self, trCode, recordName, index, itemName):
        return self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", 
        trCode, recordName, index, itemName)

    # 차트 조회한 데이터 전부를 배열로 받아온다.
    # LPCTSTR strTrCode : 조회한TR코드
    # LPCTSTR strRecordName: 조회한 TR명
    # ※항목의 위치는 KOA Studio의 TR목록 순서로 데이터를 가져옵니다.
    # 예로 OPT10080을 살펴보면 OUTPUT의 멀티데이터의 항목처럼 현재가, 거래량, 체결시간등 순으로 항목의 위치가 0부터 1씩증가합니다.
    @pyqtSlot(str, str, result=str)
    def getCommDataEx(self, trCode, recordName):
        return self.ocx.dynamicCall("GetCommDataEx(QString, QString)", trCode, recordName)

    # 리얼 시세를 끊는다.
    # 화면 내 모든 리얼데이터 요청을 제거한다.
    # 화면을 종료할 때 반드시 위 함수를 호출해야 한다.
    # Ex) openApi.DisconnectRealData(“0101”);
    @pyqtSlot(str)
    def disconnectRealData(self, scnNo):
        self.ocx.dynamicCall("DisconnectRealData(QString)", scnNo)

    # 종목코드의 한글명을 반환한다.
    # strCode – 종목코드
    # 종목한글명
    # 없는 코드 일경우 empty 를 리턴함 
    @pyqtSlot(str, result=str)
    def getMasterCodeName(self, strCode):
        return self.ocx.dynamicCall("GetMasterCodeName(QString)", strCode)


if __name__ == "__main__":
    def test_buy():
        # 비정상 매수 (시장가에 단가 넣기 ) 우리종금 1주  
        # objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매수"], 
        # "010050", 1, 900 , kw_util.dict_order["시장가"], "")

        # 정상 매수 - kd 건설 1주 
        objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매수"], 
        "044180", 1, 0 , kw_util.dict_order["시장가"], "")
        pass

    def test_sell():
        #정상 매도 - kd 건설 1주 
        objKiwoom.sendOrder("sell", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
        "044180", 1, 0 , kw_util.dict_order["시장가"], "")
        pass

    def test_condition():
        objKiwoom._OnReceiveRealCondition("044180", "I",  "단타 추세", 1)
        pass
    def test_getCodeList():
        # 코스피 코드 리스트
        result = objKiwoom.getCodeListByMarket('0')
        print(result)
        # 코스닥 코드 리스트 
        result = objKiwoom.getCodeListByMarket('10')
        print(result)
        pass
    def test_jusikGibon():
        objKiwoom.requestOpt10001("044180")
        pass
    def test_jusik_condition_occur():
        objKiwoom.addConditionOccurList('044180')
        pass

    @pyqtSlot()
    def test_make_jangoInfo():
        objKiwoom.makeJangoInfoFile()
        pass
    def test_make_chegyeolInfo():
        objKiwoom.makeChegyeolInfoFile()
    def test_terminate():
        objKiwoom.sigTerminating.emit()
        pass
    
    def test_make_excel():
        file_path = r'd:\download\통합 문서2.xlsx'
        test_data = {  
            "170822": [
                "      8.56|      8750| 매수횟수: 1 | (익절이다) | 210540 | -매도 |      22200 |       5 | 141905 | 디와이파워 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 038870 | +매수 |      10350 |      10 | 142205 | 에코바이오 "
            ],
            "170824": [
                "      8.81|      9180| 매수횟수: 1 | (익절이다) | 033100 | -매도 |       6300 |      18 | 090136 | 제룡전기 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 069540 | +매수 |       6200 |      17 | 090349 | 라이트론 ",
                "      8.55|      9010| 매수횟수: 1 | (익절미달) | 069540 | -매도 |       6730 |      17 | 090557 | 라이트론 ",
                "      8.76|      8925| 매수횟수: 1 | (익절미달) | 226350 | -매도 |       3165 |      35 | 090842 | 아이엠텍 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 180400 | +매수 |      14250 |       8 | 091259 | 엠지메드 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 072470 | +매수 |       8247 |      13 | 091845 | 우리산업홀딩스 ",
                "         0|         0| 매수횟수: 4 | (단순매수) | 031860 | +매수 |       5050 |      80 | 094752 | 엔에스엔 "
            ],
            "170914": [
                "     13.53|     14000| 매수횟수: 1 | (익절이다) | 038870 | -매도 |      11750 |      10 | 090102 | 에코바이오 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 023800 | +매수 |       6400 |       8 | 090105 | 인지컨트롤스 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 042600 | +매수 |       8420 |       6 | 090113 | 새로닉스 ",
                "      8.99|      4720| 매수횟수: 1 | (익절미달) | 161570 | -매도 |       7150 |       8 | 093611 | 미동앤씨네마 ",
                "         0|         0| 매수횟수: 1 | (단순매수) | 005420 | +매수 |      19050 |       3 | 093933 | 코스모화학 "
            ]
        }
        objKiwoom.make_excel(file_path, test_data)

    # putenv 는 current process 에 영향을 못끼치므로 environ 에서 직접 세팅 
    # qml debugging 를 위해 QML_IMPORT_TRACE 환경변수 1로 세팅 후 DebugView 에서 디버깅 메시지 확인 가능  
    os.environ['QML_IMPORT_TRACE'] = '1'
    # print(os.environ['QML_IMPORT_TRACE'])
    myApp = QtWidgets.QApplication(sys.argv)
    objKiwoom = KiwoomConditon()

    form = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(form)

    event_filter = CloseEventEater()
    form.installEventFilter( event_filter )

    ui.btnMakeExcel.clicked.connect(objKiwoom.onBtnMakeExcelClicked )
    ui.btnStart.clicked.connect(objKiwoom.onBtnStartClicked)

    ui.btnYupjong.clicked.connect(objKiwoom.onBtnYupjongClicked)
    ui.btnJango.clicked.connect(objKiwoom.onBtnJangoClicked)
    ui.btnChegyeol.clicked.connect(objKiwoom.onBtnChegyeolClicked)
    ui.btnCondition.clicked.connect(objKiwoom.onBtnConditionClicked)

    ui.lineCmd.textChanged.connect(objKiwoom.onLineCmdTextChanged)
    ui.btnRun.clicked.connect(objKiwoom.onBtnRunClicked)

    form.show()

    sys.exit(myApp.exec_())