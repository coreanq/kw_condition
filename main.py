# -*-coding: utf-8 -
import sys, os, re, datetime, copy, json
import resource_rc

import util, kw_util

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl, QEvent
from PyQt5.QtCore import QStateMachine, QState, QTimer, QFinalState
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from mainwindow_ui import Ui_MainWindow

TEST_MODE = True    # 주의 TEST_MODE 를 False 로 하는 경우, TOTAL_BUY_AMOUNT 만큼 구매하게 됨  
# AUTO_TRADING_OPERATION_TIME = [ [ [9, 10], [10, 00] ], [ [14, 20], [15, 10] ] ]  # ex) 9시 10분 부터 10시까지 14시 20분부터 15시 10분 사이에만 동작 
AUTO_TRADING_OPERATION_TIME = [ [ [9, 1], [15, 19] ] ] #해당 시스템 동작 시간 설정

# DAY_TRADING_END_TIME 시간에 모두 시장가로 팔아 버림  반드시 동시 호가 시간 5분전으로 입력해야함 
# auto_trading_operation_time 이전값을 잡아야 함 
DAY_TRADING_ENABLE = True
DAY_TRADING_END_TIME = [15, 10] 

TRADING_INFO_GETTING_TIME = [15, 35] # 트레이딩 정보를 저장하기 시작하는 시간
STOP_LOSS_VALUE_DAY_RANGE = 4 # stoploss 의 값은 stop_loss_value_day_range 중 저가로 계산됨 ex) 10이면 10일중 저가 

CONDITION_NAME = '거래량' #키움증권 HTS 에서 설정한 조건 검색 식 총이름
TOTAL_BUY_AMOUNT = 10000000 #  매도 호가1, 2 총 수량이 TOTAL_BUY_AMOUNT 이상 안되면 매수금지  (슬리피지 최소화)
TIME_CUT_MIN = 9999 # 타임컷 분값으로 해당 TIME_CUT_MIN 분 동안 가지고 있다가 시간이 지나면 손익분기점으로 손절가를 올림  

#익절 계산하기 위해서 slippage 추가하며 이를 계산함  
STOP_PLUS_VALUE =  1.0
STOP_LOSS_VALUE = 1.5 # 매도시  같은 값을 사용하는데 손절 잡기 위해서 슬리피지 포함아여 적용 

SLIPPAGE = 0.5 # 기본 매수 매도시 슬리피지는 0.5 이므로 +  수수료 0.5  

TR_TIME_LIMIT_MS = 3800 # 키움 증권에서 정의한 연속 TR 시 필요 딜레이 
CHUMAE_LIMIT = 2 # 추가 매수 제한 

ETF_BUY_QTY = 1
# 장기 보유 종목 번호 리스트 
ETF_LIST = {
    '114800': "kodex 인버스",
    '069500': "kodex 200"
}
ETF_PAIR_LIST = {
    '114800':'069500',
    '069500':'114800'
}
# 장기 보유 종목 번호 리스트 
EXCEPTION_LIST = ['034220']
STOCK_POSSESION_COUNT = 10 + len(EXCEPTION_LIST) + 2 # etf +2 

ONE_MIN_CANDLE_EXCEL_FILE_PATH = "log" + os.path.sep + util.cur_date() + "_1min_stick.xlsx" 
CHEGYEOL_INFO_FILE_PATH = "log" + os.path.sep +  "chegyeol.json"
JANGO_INFO_FILE_PATH =  "log" + os.path.sep + "jango.json"

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
    sigRequestYupjongInfo = pyqtSignal()

    sigGetBasicInfo = pyqtSignal()
    sigGetYupjong5minInfo = pyqtSignal()
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
        self.etf_profit  = 0
        
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
        initSystemState.addTransition(self.sigGetConditionCplt, waitingTradeSystemState)
        waitingTradeSystemState.addTransition(self.sigWaitingTrade, waitingTradeSystemState )
        waitingTradeSystemState.addTransition(self.sigSelectCondition, requestingJangoSystemState)
        requestingJangoSystemState.addTransition(self.sigRequestJangoComplete, calculateStoplossSystemState)
        calculateStoplossSystemState.addTransition(self.sigCalculateStoplossComplete, standbySystemState)
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
        requestYupjong5minInfoProcessBuyState = QState(processBuyState)
        request5minInfoProcessBuyState = QState(processBuyState)
        determineBuyProcessBuyState = QState(processBuyState)
        waitingTRlimitProcessBuyState = QState(processBuyState)

        processBuyState.setInitialState(initProcessBuyState)
        initProcessBuyState.addTransition(self.sigStartProcessBuy, standbyProcessBuyState)

        standbyProcessBuyState.addTransition(self.sigConditionOccur, standbyProcessBuyState)
        standbyProcessBuyState.addTransition(self.sigRequestYupjongInfo, requestYupjong5minInfoProcessBuyState)
        standbyProcessBuyState.addTransition(self.sigStopProcessBuy, initProcessBuyState)

        requestYupjong5minInfoProcessBuyState.addTransition(self.sigGetYupjong5minInfo, waitingTRlimitProcessBuyState)
        requestYupjong5minInfoProcessBuyState.addTransition(self.sigRequestInfo, request5minInfoProcessBuyState)
        requestYupjong5minInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState )

        request5minInfoProcessBuyState.addTransition(self.sigGet5minInfo, determineBuyProcessBuyState)
        request5minInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState )

        determineBuyProcessBuyState.addTransition(self.sigNoBuy, waitingTRlimitProcessBuyState)
        determineBuyProcessBuyState.addTransition(self.sigBuy, waitingTRlimitProcessBuyState)

        waitingTRlimitProcessBuyState.addTransition(self.sigTrWaitComplete, standbyProcessBuyState)

        processBuyState.entered.connect(self.processBuyStateEntered)
        initProcessBuyState.entered.connect(self.initProcessBuyStateEntered)
        standbyProcessBuyState.entered.connect(self.standbyProcessBuyStateEntered)
        requestYupjong5minInfoProcessBuyState.entered.connect(self.requestYupjong5minInfoProcessBuyStateEntered)
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
    def onBtnStartClicked(self):
        print(util.whoami())
        self.sigInitOk.emit()
        
    @pyqtSlot()
    def onBtnRestartClicked(self):
        print(util.whoami())

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
        print(items)
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
        # 장시작 30 분전에 조건이 시작하도록 함 
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

        # def requestFunc(jongmokCode):
        #     def inner():
        #         self.requestOpt10081(jongmokCode)
        #     return inner
        # request_jongmok_codes = []
        # for jongmok_code in self.jangoInfo.keys():
        #     jango_info = self.jangoInfo[jongmok_code]
        #     if( '손절가' not in jango_info.keys() ):
        #         request_jongmok_codes.append( jongmok_code )

        # if( len(request_jongmok_codes) == 0 ):
        #     self.sigCalculateStoplossComplete.emit()
        # else:
        #     # 요청은 1초에 5개뿐이므로 200 ms 나눠서 함 너무 200 딱맞추면 오류 나므로 여유 줌  
        #     for index, jongmok_code in enumerate(request_jongmok_codes):
        #         func = requestFunc(jongmok_code) 
        #         QTimer.singleShot(220 * (index + 1), func)
        #     pass

    @pyqtSlot()
    def standbySystemStateEntered(self):
        print(util.whoami() )
        # 프로그램 첫 시작시 TR 요청으로 인한 제한 시간  막기 위해 딜레이 줌 
        QTimer.singleShot(TR_TIME_LIMIT_MS * 5, self.sigStartProcessBuy)
        pass

    @pyqtSlot()
    def terminatingSystemStateEntered(self):
        print(util.whoami() )
        if( '069500' not in self.jangoInfo):
            self.buy_etf('normal', ETF_BUY_QTY)
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

        for jongmok_code in self.conditionRevemoList:
            self.removeConditionOccurList(jongmok_code)
        self.conditionRevemoList.clear()

        self.refreshRealRequest()

        jongmok_info = self.getConditionOccurList()

        if( jongmok_info ):
            self.sigRequestInfo.emit()
            print(util.whoami() , jongmok_info['종목명'], jongmok_info['종목코드'])
        pass

    @pyqtSlot()
    def requestYupjong5minInfoProcessBuyStateEntered(self):
        print(util.whoami())
        if( '5분 0봉전' not in self.yupjongInfo['코스피'] or '5분 0봉전' not in self.yupjongInfo['코스닥']):
            self.sigError.emit()
            return

        time_span = datetime.timedelta(minutes = 5)

        chegyeol_time_str = self.yupjongInfo['코스피']['5분 0봉전']['체결시간']   #140359 
        target_time = datetime.datetime.strptime(chegyeol_time_str, "%H%M%S") + time_span
        
        if( datetime.datetime.now() > target_time ):
            self.requestOpt20005('001')
            return

        chegyeol_time_str = self.yupjongInfo['코스닥']['5분 0봉전']['체결시간']   #140359 
        target_time = datetime.datetime.strptime(chegyeol_time_str, "%H%M%S") + time_span

        if( datetime.datetime.now() > target_time ):
            self.requestOpt20005('101')
            return
        self.sigrequestInfo.emit()
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
        # 혹은 집입했닥 아틸하면 데이터 삭제 하므로 실시간 정보가 없을수도 있다. 
        if( '매도호가1' not in jongmok_info_dict or '등락율' not in jongmok_info_dict ):
            self.shuffleConditionOccurList()
            if( '매도호가1' not in jongmok_info_dict ):
                print('매도호가1 not in {0}'.format(code))
            else:
                print('등락율 not in {0}'.format(code))
            QTimer.singleShot(500, self.sigError)
            return

        if( self.requestOpt10080(code) == False ):
            QTimer.singleShot(500, self.sigError)

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
        elif( jongmokCode in self.jangoInfo ):
        # 중복매수는 예외 
            pass
        else:
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
        # 가격조건 확인 
        # if( maedoHoga1 >= STOCK_PRICE_MIN_MAX['min'] and maedoHoga1 <= ['max']):
        #     pass
        # else:
        #     printLog += '(종목가격미충족: 매도호가1 {0})'.format(maedoHoga1)
        #     return_vals.append(False)
        

        ##########################################################################################################
        # 호가 잔량이 살만큼 있는 경우  
        totalAmount = maedoHoga1 * maedoHogaAmount1 + maedoHoga2 * maedoHogaAmount2
        if( totalAmount >= TOTAL_BUY_AMOUNT):
            pass 
        else:
            printLog += '(호가수량부족: 매도호가1 {0} 매도호가잔량1 {1})'.format(maedoHoga1, maedoHogaAmount1)
            return_vals.append(False)

    
        ##########################################################################################################
        # 5분봉 1봉전 거래량에 비해 0봉전 거래량 비율 체크  
        amount_index = kw_util.dict_jusik['TR:분봉'].index('거래량')
        before0_amount = abs(int(jongmok_info_dict['5분 0봉전'][amount_index]))
        before1_amount = abs(int(jongmok_info_dict['5분 1봉전'][amount_index]))

        current_price_index =  kw_util.dict_jusik['TR:분봉'].index('현재가')
        before0_price = abs(int(jongmok_info_dict['5분 0봉전'][current_price_index]))
        before1_price = abs(int(jongmok_info_dict['5분 1봉전'][current_price_index]))

        
        # 추가 매수시 매입가보다 큰 경우 추가 매수 금지 
        maeip_price = 9999999
        if( jongmokCode in self.jangoInfo):
            maeip_price = int(self.jangoInfo[jongmokCode]['매입가'])
        
        if( 
            before0_amount > before1_amount * 2 and  # 거래량 2배 조건 반드시 넣기 
            before0_amount > 5000 and  # 거래량이 너무 최소인 경우를 막기 위함 
            maedoHoga1 <  maeip_price 
        ):
            printLog += '(5분봉 충족: 거래량 {0}% 0: price({1}/{2}), 1: ({3}/{4})'.format(
                int(before0_amount / before1_amount * 100), 
                before0_price , before0_amount, 
                before1_price, before1_amount
                )
            pass
        else:
            printLog += '(5분봉 미충족: 거래량 {0}% 0: price({1}/{2}), 1: ({3}/{4})'.format(
                int(before0_amount / before1_amount * 100), 
                before0_price , before0_amount, 
                before1_price, before1_amount
                )
            return_vals.append(False)

        ##########################################################################################################
        # rsi 조건 미충족  
        is_rsi = False
        rsi_14 = int( float(jongmok_info_dict['RSI14']) )
        if( rsi_14 < 45):
            printLog += '(rsi 충족: {0})'.format( rsi_14 )
            pass
        else:
            printLog += '(rsi 미충족: {0})'.format( rsi_14 )
            return_vals.append(False)

        ##########################################################################################################
        # 개별 주식 이동평균선 조건 판단  
        twentybong_avr = int(jongmok_info_dict['20봉평균'])
        fivebong_avr = int(jongmok_info_dict['5봉평균'])
        if(
            twentybong_avr > fivebong_avr and
            maedoHoga1 < twentybong_avr 
        ):
            printLog += '(이평 충족: 20: {0}, 5: {1})'.format( twentybong_avr, fivebong_avr )
            is_avr = True 
            pass
        else:
            printLog += '(이평 미충족: 20: {0}, 5: {1})'.format( twentybong_avr, fivebong_avr )
            return_vals.append(False)
        
        if( is_rsi and is_avr ):
            is_log_print_enable = True

        ##########################################################################################################
        # 업종 이동 평균선 조건 판단 
        if( jongmokCode in  self.kospiCodeList):
            yupjong_name = '코스피'
            twentybong_avr = float(self.yupjong_info[yupjong_name]['20봉평균'])
            fivebong_avr = float(self.yupjongInfo[yupjong_name]['5봉평균'])
            if( fivebong_avr > twentybong_avr ):
                printLog +='({0}이평조건충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
            else:
                printLog +='({0}이평조건미충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
                return_vals.append(False)
            pass
        else: 
            yupjong_name = '코스닥'
            twentybong_avr = float(self.yupjong_info[yupjong_name]['20봉평균'])
            fivebong_avr = float(self.yupjongInfo[yupjong_name]['5봉평균'])
            if( fivebong_avr > twentybong_avr ):
                printLog +='({0}이평조건충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
            else:
                printLog +='({0}이평조건미충족: 20봉평균: {1}, 5봉평균: {2})'.format(yupjong_name, twentybong_avr, fivebong_avr)
                return_vals.append(False)
            pass

        ##########################################################################################################
        # 5분 0봉전 시간과 체결시간 비교하여 5분 초과한경우만 매수 (동일 5분봉에서 추가 매수 금지 하기 위함)
        if( jongmokCode in self.jangoInfo):
            chegyeol_time_str = self.jangoInfo[jongmokCode]['주문/체결시간'] #20170411151000
            time_span = datetime.timedelta(minutes = 30 )
            
            if( chegyeol_time_str != ''):
                target_time = datetime.datetime.strptime(chegyeol_time_str, "%Y%m%d%H%M%S") + time_span
                if( datetime.datetime.now() > target_time ):
                    pass
                else:
                    printLog += '(30분내 추가매수 발생)'
                    return_vals.append(False)

        ##########################################################################################################
        #  추가 매수 제한   
        chumae_count = 0
        if( jongmokCode in self.jangoInfo):
            chumae_count = int(self.jangoInfo[jongmokCode]['추가매수횟수'])
        if( chumae_count < CHUMAE_LIMIT ):
            printLog += '(추가매수 {0})'.format(chumae_count)
            pass
        else:
            printLog += '(추가매수한계)'
            return_vals.append(False)

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
        #     updown_percentage = float(self.yupjong_info['코스피'].get('등락율', -99) )
        #     if( updown_percentage < -0.2 ) :
        #         printLog +='(코스피등락율미충족: 등락율 {0})'.format(updown_percentage)
        #         return_vals.append(False)
        #     pass
        # else: 
        #     updown_percentage = float(self.yupjong_info['코스닥'].get('등락율', -99) )
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
            maesu_amount = 0
            if( TEST_MODE == True ):
                maesu_amount = 1
            else:
                maesu_amount = round((TOTAL_BUY_AMOUNT / maedoHogaAmount2) - 0.5) # 첫번째 자리수 버림

            if( chumae_count <= 1 ):
                qty = maesu_amount 
                pass
            else:
                qty = maesu_amount * (2 ** (chumae_count - 1))

            result = self.sendOrder("buy_" + jongmokCode, kw_util.sendOrderScreenNo, 
                                objKiwoom.account_list[0], kw_util.dict_order["신규매수"], jongmokCode, 
                                qty, 0 , kw_util.dict_order["시장가"], "")
            print("B " + str(result) , sep="")
            printLog = ' 현재가:{0} '.format(maedoHoga1) + printLog
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
        sys.exit()
        pass


    def sendorder_multi(self, rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo):
        def inner():
            self.sendOrder(rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo)
        return inner

    def buy_etf(self, type, qty):
        #etf 매수
        req_num = 0 # 주문이 다수이므로 1초에 5개 주문을 지키기 위해 사용
        rQName, code, price, orgOrderNo = '', '','',''

        accNo = self.account_list[0]
        orderType = kw_util.dict_order["신규매수"]
        hogaGb =  kw_util.dict_order["시장가"]
        price = 0

        # 거래량 부족으로 시장가 매도 해도 모의 투자 처럼 팔리지 않음 
        if( type == '2x' or type == 'all'):
            # rQName, code, req_num = 'buy1', '122630', req_num +1
            # func = self.sendorder_multi(rQName, screenNo, accNo, orderType, code, qty * 3, price, hogaGb, orgOrderNo) 
            # QTimer.singleShot(210 * (req_num - 1), func)

            # rQName, code, req_num = 'buy2', '252670', req_num +1
            # func = self.sendorder_multi(rQName, screenNo, accNo, orderType, code, qty * 2, price, hogaGb, orgOrderNo) 
            # QTimer.singleShot(210 * (req_num - 1), func)
            pass

        # kodex 200 과 kodex 인버스의 경우 4배 차이가 나므로 수량차이가 남 
        if( type == 'normal' or type == 'all'):
            rQName, code, req_num = 'buy3', '114800', req_num +1
            screenNo = kw_util.sendOrderETFScreenNo
            func = self.sendorder_multi(rQName, screenNo, accNo, orderType, code, qty * 4, price, hogaGb, orgOrderNo) 
            QTimer.singleShot(210 * (req_num - 1), func)

            rQName, code, req_num = 'buy4', '069500', req_num +1
            screenNo = kw_util.sendOrderETFPairScreenNo
            func = self.sendorder_multi(rQName, screenNo, accNo, orderType, code, qty, price, hogaGb, orgOrderNo) 
            QTimer.singleShot(210 * (req_num - 1), func)
            pass

    def sell_etf(self, type, normal_price = '0', inverse_price = '0') :
        #etf 매도이며 1초에 5번 주문 제한 상관안하고 바로 매도 주문 내도록 함 ( 타이밍 중요하며 동시에 5개 이상 나갈일도 없음 ) 
        req_num = 0
        rQName, code, price, orgOrderNo = '', '','',''

        accNo = self.account_list[0]
        orderType = kw_util.dict_order["신규매도"]
        if( price  == 0 ):
            hogaGb =  kw_util.dict_order["시장가"]
        else:
            hogaGb =  kw_util.dict_order["지정가"]

        if( normal_price == '0' ):
            normal_price = self.jangoInfo['069500']['매수호가1']
            inverse_price = self.jangoInfo['114800']['매수호가1']
 
        normal_price = normal_price.replace('-', '')
        normal_price = normal_price.replace('+', '')
        inverse_price = inverse_price.replace('-', '')
        inverse_price = inverse_price.replace('+', '')

        if( type == 'normal' or type == 'all'):
            rQName, code, req_num = 'sell3', '114800', req_num +1
            qty = self.jangoInfo['114800']['매매가능수량']
            screenNo = kw_util.sendOrderETFScreenNo
            if( '매도중' not in self.jangoInfo['114800']):
                self.jangoInfo['114800']['매도중'] = True
                self.sendOrder(rQName, screenNo, accNo, orderType, code, qty, inverse_price , hogaGb, orgOrderNo) 

            rQName, code, req_num = 'sell4', '069500', req_num +1
            qty = self.jangoInfo['069500']['매매가능수량']
            screenNo = kw_util.sendOrderETFPairScreenNo
            if( '매도중' not in self.jangoInfo['069500']):
                self.jangoInfo['069500']['매도중'] = True
                self.sendOrder(rQName, screenNo, accNo, orderType, code, qty, normal_price, hogaGb, orgOrderNo) 
        pass

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

        ret = self.commRqData(account_num, "opw00018", 0, kw_util.sendJusikAccountInfoScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString =   account_num + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True

        pass

    # 주식 1일봉 요청 
    def requestOpt10081(self, jongmokCode):
        # print(util.cur_time_msec() )
        datetime_str = datetime.datetime.now().strftime('%Y%m%d')
        self.setInputValue("종목코드", jongmokCode)
        self.setInputValue("기준일자", datetime_str)    
        self.setInputValue('수정주가구분', '0')
        ret = self.commRqData(jongmokCode, "opt10081", 0, kw_util.sendJusikGibonScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString = jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True
        
    # 주식 분봉 tr 요청 
    def requestOpt10080(self, jongmokCode):
     # 분봉 tr 요청의 경우 너무 많은 데이터를 요청하므로 한개씩 수행 
        self.setInputValue("종목코드", jongmokCode )
        self.setInputValue("틱범위","5:5분") 
        self.setInputValue("수정주가구분","0") 
        # rQName 을 데이터로 외부에서 사용
        ret = self.commRqData(jongmokCode , "opt10080", 0, kw_util.sendminTrScreenNo) 
        
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

        fivebong_sum = 0
        twentybong_sum = 0 
        for i in range(min(repeatCnt, 20)):
            line = []
            for item_name in kw_util.dict_jusik['TR:분봉']:
                result = self.getCommData("opt10080", rQName, i, item_name)

                if( item_name == "현재가"):
                    if( i < 5 ):
                        fivebong_sum += abs(int(result))
                        pass
                    twentybong_sum += abs(int(result))
                line.append(result.strip())
            # print(line)
            # 오늘 이전 데이터는 받지 않는다 --> 장시작시는 전날 데이터도 필요 하므로 삭제 
            # resultTime = time.strptime(currentTimeStr,  "%Y%m%d%H%M%S")
            # currentTime = time.localtime()
            # if( resultTime.tm_mday == currentTime.tm_mday ):
            #     key_value = '5분 {0}봉전'.format(i)
            #     jongmok_info_dict[key_value] = linegg
            # else:
            #     break
            key_value = '5분 {0}봉전'.format(i)
            jongmok_info_dict[key_value] = line
        
        jongmok_info_dict['20봉평균'] = str(int(twentybong_sum / 20))
        jongmok_info_dict['5봉평균'] = str(int(fivebong_sum / 5))

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
        rsi_value = round(rsi_up_avg / ( rsi_up_avg + rsi_down_avg ) * 100 , 1)
        jongmok_info_dict['RSI14'] = str(rsi_value)
        # print(util.whoami(), jongmok_info_dict['종목코드'], 'rsi_value: ',  jongmok_info_dict['RSI14'])
        return True

    # 업종 분봉 tr 요청 
    def requestOpt20005(self, yupjong_code):
        self.setInputValue("종목코드", yupjong_code )
        self.setInputValue("틱범위","5:5분") 
        self.setInputValue("수정주가구분","0") 
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
        yupjong_info_dict = self.yupjongInfo[rQName]

        repeatCnt = self.getRepeatCnt("opt20005", rQName)

        fivebong_sum = 0
        twentybong_sum = 0 
        for i in range(min(repeatCnt, 20)):
            line = []
            for item_name in kw_util.dict_jusik['TR:업종분봉']:
                result = self.getCommData("opt20005", rQName, i, item_name)
                if( item_name == "현재가"):
                    if( i < 5 ):
                        fivebong_sum += abs(int(result))
                        pass
                    twentybong_sum += abs(int(result))
                line.append(result.strip())
            key_value = '5분 {0}봉전'.format(i)
            yupjong_info_dict[key_value] = line
        
        yupjong_info_dict['20봉평균'] = str(int(twentybong_sum / 20))
        yupjong_info_dict['5봉평균'] = str(int(fivebong_sum / 5))
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
        print(util.whoami() + 'sScrNo: {}, rQName: {}, trCode: {}' 
        .format(scrNo, rQName, trCode))

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

        #주식 기본 정보 요청 
        # rQName 은 개별 종목 코드임
        elif( trCode == "opt10001"):
            if( self.makeOpt10001Info(rQName) ):
                self.sigGetBasicInfo.emit()
            else:
                self.sigError.emit()
            pass

        # 주식 분봉 rQName 개별 종목 코드  
        elif( trCode == "opt10080"):     
            if( self.makeOpt10080Info(rQName) ) :
                self.sigGet5minInfo.emit()
            else:
                self.sigError.emit()
            pass

        # 업종 분봉 rQName 업종 코드  
        elif( trCode == "opt20005"):     
            if( self.makeOpt20005Info(rQName) ) :
                self.sigGetYupjong5minInfo.emit()
            else:
                self.sigError.emit()
            pass

    # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmokCode, realType, realData):
        # print(util.whoami() + 'jongmokCode: {}, {}, realType: {}'
        #         .format(jongmokCode, self.getMasterCodeName(jongmokCode),  realType))
        jongmok_name = self.getMasterCodeName(jongmokCode) 
        # 장전에도 주식 호가 잔량 값이 올수 있으므로 유의해야함 
        if( realType == "주식호가잔량"):
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))

            self.makeHogaJanRyangInfo(jongmokCode)                

            ########################################################################
            # 여기서부터는 ETF 전용 
            if( jongmokCode not in ETF_LIST or jongmokCode not in self.jangoInfo):
                return
            maesuHoga1 = abs(int(self.jangoInfo[jongmokCode]['매수호가1']))
            # 매수 호가 기준으로 수익 측정 
            self.calculateSuik(jongmokCode, maesuHoga1)

            printData = ''
            pair_etf_code = ETF_PAIR_LIST[jongmokCode]

            # 하나라도 매도 되었다면 
            if( jongmokCode not in self.jangoInfo or pair_etf_code not in self.jangoInfo ):
                return
            
            # 첫 수익 종목 읽을 시 기본 종목 pair 종목 모두 수익 key 값이 존재 하지 않는다면 
            if( '수익' not in self.jangoInfo[jongmokCode] or '수익' not in self.jangoInfo[pair_etf_code]):
                return

            pair_jongmok_name = self.getMasterCodeName(pair_etf_code)
            jongmok_suik= int(self.jangoInfo[jongmokCode]['수익'])
            pair_jongmok_suik = int(self.jangoInfo[pair_etf_code]['수익'])

            profit = jongmok_suik + pair_jongmok_suik

            if( profit  >= 20):
                compare_result = ''
                jongmokMaesuHogaAmount1 = int(self.jangoInfo[jongmokCode]['매수호가수량1'])
                jongmokMaesuHogaAmount2 = int(self.jangoInfo[jongmokCode]['매수호가수량2'])
                pair_jongmokMaesuHogaAmount1 = int(self.jangoInfo[pair_etf_code]['매수호가수량1'])
                pair_jongmokMaesuHogaAmount2 = int(self.jangoInfo[pair_etf_code]['매수호가수량2'])

                jongmokMaesuHoga1 = int(self.jangoInfo[jongmokCode]['매수호가1'])
                pair_jongmokMaesuHoga1 = int(self.jangoInfo[pair_etf_code]['매수호가1'])

                if( jongmok_suik > pair_jongmok_suik ):
                    compare_result = '{0}({1:>7}) > {2}({3:>7})'.format(
                        jongmok_name, jongmokMaesuHoga1, 
                        pair_jongmok_name, pair_jongmokMaesuHoga1)
                else:
                    compare_result = '{0}({1:>7}) < {2}({3:>7})'.format(
                        jongmok_name, jongmokMaesuHoga1, 
                        pair_jongmok_name, pair_jongmokMaesuHoga1)

                printData = '{0}] 비교: ({1}), profit:{2:>8}, hoga1:{3:>7}, hoga2:{4:>7}, pair_hoga1:{5:>7}, pair_hoga2:{6:>7}'.format(
                    util.cur_time(), 
                    compare_result, profit, jongmokMaesuHogaAmount1, jongmokMaesuHogaAmount2, 
                    pair_jongmokMaesuHogaAmount1, pair_jongmokMaesuHogaAmount2
                )

                if( jongmokMaesuHogaAmount1 > 10000 and pair_jongmokMaesuHogaAmount1 > 10000):
                    print(printData, end='')
                    if( self.etf_profit != profit ):
                        self.etf_profit = profit
                        util.save_log(printData, '*** etf 이익실현 ***', 'log')
                    # WARNING: 이곳은 실시간 호가 이므로 장 전에도 실행되므로 장중에만 팔리도록 해야함 
                    if( self.isTradeAvailable() == True ):
                        if( jongmokCode == '114800' or jongmokCode == '069500'):
                            if( profit >= 40 ):
                                normal_price = self.jangoInfo['069500']['매수호가1']
                                inverse_price = self.jangoInfo['114800']['매수호가1']
                                self.sell_etf(type = 'normal', normal_price = normal_price, inverse_price = inverse_price)
                            pass
                        pass

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
            print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
                .format(jongmokCode, realType, realData))
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

        maeip_commission = maeip_price * boyou_suryang * 0.00015 # 매입시 증권사 수수료 
        current_commission = 0
        #etf 는 제세금이 없으므로 
        if( jongmok_code not in ETF_LIST ):
            maeip_commission = maeip_price * boyou_suryang * 0.00015 # 매입시 증권사 수수료 
            current_commission = current_price * boyou_suryang * 0.00315 # 매도시 증권사 수수료 + 제세금 
        else:
            #TODO: for test 나중에 증권사 수수료 적용해야함 
            maeip_commission = 0  
            current_commission = 0 
            # current_commission = current_price * boyou_suryang * 0.00015 # 매도시 증권사 수수료 

        suik_price = round( (current_price - maeip_price) * boyou_suryang - maeip_commission - current_commission , 2)
        current_jango['수익'] = suik_price 
        current_jango['수익율'] = round( (suik_price  / (maeip_price * boyou_suryang)) * 100 , 2) 
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

        jangosuryang = int( current_jango['매매가능수량'] )

        # after buy command, before stoploss calculate this routine can run 
        if( '손절가' not in current_jango or '매수호가1' not in current_jango):
            return

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
        current_time = datetime.datetime.now()
        time_span = datetime.timedelta(minutes = TIME_CUT_MIN )
        chegyeol_time = current_jango['주문/체결시간']

        if( chegyeol_time != ''):
            maeip_time = datetime.datetime.strptime(chegyeol_time, '%Y%m%d%H%M%S')
        else: 
            maeip_time = datetime.datetime.now()

        if( maeip_time < current_time - time_span ):
            stop_loss = int(current_jango['매입가'] ) 


        #########################################################################################
        # 추가 매수 횟수 리미트 시 손절가를 매입가로 올림 
        # chumae_count = int(self.jangoInfo[jongmokCode]['추가매수횟수'])
        # if( chumae_count == CHUMAE_LIMIT ):
        #     stop_loss = int(current_jango['매입가'] ) 


        #########################################################################################
        # day trading 용 
        if( jongmokCode in ETF_LIST and DAY_TRADING_ENABLE == True ):
            # day trading 주식 거래 시간 종료가 가까운 경우 모든 종목 매도 
            time_span = datetime.timedelta(minutes = 10 )
            dst_time = datetime.datetime.combine(datetime.date.today(), datetime.time(*DAY_TRADING_END_TIME)) + time_span

            current_time = datetime.datetime.now()
            if( datetime.time(*DAY_TRADING_END_TIME) <  current_time.time() and dst_time > current_time ):
                # 0 으로 넣고 로그 남기면서 매도 처리하게 함  
                # stop_loss = 0  
                pass

        # 손절 / 익절 계산 
        # 정리나, 손절의 경우 시장가로 팔고 익절의 경우 보통가로 팜 
        isSijanga = False
        if( stop_loss == 0 ):
            printData+= "(정리)"
            isSijanga = True
            isSell = True
        elif( stop_loss >= maesuHoga1 ) :
            printData += "(손절)"
            isSijanga = True
            isSell = True
        elif( stop_plus < maesuHoga1 ) :
            if( totalAmount >= TOTAL_BUY_AMOUNT):
                printData += "(익절)" 
                isSell = True 
            else:
                printData += "(익절조건미달)" 
                isSell = True

        printData +=    ' 손절가: {0:7}/'.format(str(stop_loss)) + \
                        ' 이익실현가: {0:7}/'.format(str(stop_plus)) + \
                        ' 매입가: {0:7}/'.format(str(maeipga)) + \
                        ' 잔고수량: {0:7}'.format(str(jangosuryang)) +\
                        ' 주문/체결시간: {0:7}'.format(chegyeol_time) + \
                        ' 매수호가1 {0:7}/'.format(str(maesuHoga1)) + \
                        ' 매수호가수량1 {0:7}/'.format(str(maesuHogaAmount1)) + \
                        ' 매수호가2 {0:7}/'.format(str(maesuHoga2)) + \
                        ' 매수호가수량2 {0:7}/'.format(str(maesuHogaAmount2)) 

        if( isSell == True ):
            # processStop 의 경우 체결될때마다 호출되므로 중복 주문이 나가지 않게 함 
            if( '매도중' not in current_jango):
                current_jango['매도중'] = True
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
            jongmok_code = self.getChejanData(9001)[1:]
            boyou_suryang = int(self.getChejanData(930))
            jumun_ganeung_suryang = int(self.getChejanData(933))
            maeip_danga = int(self.getChejanData(931))
            jongmok_name= self.getChejanData(302)

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

                if( jongmok_code in ETF_LIST or jongmok_code in EXCEPTION_LIST):
                    current_jango['주문/체결시간'] = '' 
                else:
                    current_jango['주문/체결시간'] = util.cur_date_time('%Y%m%d%H%M%S')

                if( jongmok_code not in self.jangoInfo):
                    self.jangoInfo[jongmok_code] = current_jango 
                    self.jangoInfo[jongmok_code]['추가매수횟수'] = '1' 
                else:
                    chumae_count = int(self.jangoInfo[jongmok_code]['추가매수횟수'])
                    self.jangoInfo[jongmok_code]['추가매수횟수'] = str(chumae_count + 1)
                    self.jangoInfo[jongmok_code].update(current_jango)

            self.makeEtcJangoInfo(jongmok_code)
            self.makeJangoInfoFile()
            pass

        elif ( gubun == "0"):
            jumun_sangtae =  self.getChejanData(913)
            jongmok_code = self.getChejanData(9001)[1:]
            # 매수나 매도나 
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
            # 손절가 다시 계산 
            if( jongmok_code not in ETF_LIST ):
                current_jango['손절가'] = round( maeip_price *  (1 - ((STOP_LOSS_VALUE - SLIPPAGE) / 100) ) , 2 )
                current_jango['이익실현가'] = round( maeip_price *  (1 + ((STOP_PLUS_VALUE +  SLIPPAGE) / 100) ) , 2 )
            else:
                current_jango['손절가'] = 1 
                current_jango['이익실현가'] = 99999999 

            if( '주문/체결시간' not in current_jango ):
                if( jongmok_code in self.jangoInfoFromFile):
                    current_jango['주문/체결시간'] = self.jangoInfoFromFile[jongmok_code].get('주문/체결시간', '')
                else:
                    current_jango['주문/체결시간'] = ''      

            if( '추가매수횟수' not in current_jango ):
                if( jongmok_code in self.jangoInfoFromFile):
                    current_jango['추가매수횟수'] = self.jangoInfoFromFile[jongmok_code].get('추가매수횟수', '1')
                else:
                    current_jango['추가매수횟수']  = '1'
                    pass

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
                        '거래량', '등락율', '전일대비' ]
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

        nFid = kw_util.name_fid['매도매수구분']
        if( str(nFid) in fids):
            result = self.getChejanData(nFid).strip()
            if( int(result) == 1): #매도
                current_jango = self.jangoInfo[jongmok_code]

                # 체결가를 통해 수익율 필드 업데이트 
                current_price = int(self.getChejanData(kw_util.name_fid['체결가']).strip())
                self.calculateSuik(jongmok_code, current_price)

                # 매도시 체결정보는 수익율 필드가 존재 
                profit = current_jango.get('수익', '0')
                profit_percent = current_jango.get('수익율', '0' )
                info.append('{0:>10}'.format(profit_percent))
                info.append('{0:>10}'.format(profit))
                pass
            else: #매수 
                # 매수시 체결정보는 수익율 / 수익 필드가 없음  
                info.append('{0:>10}'.format('0'))
                info.append('{0:>10}'.format('0'))


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
                if( col_name == '체결가' or col_name == '체결량' or col_name == '미체결수량'):
                    result = '{0:>10}'.format(result)
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
        # print(util.whoami() + 'code: {}, type: {}, conditionName: {}, conditionIndex: {}'
        # .format(code, type, conditionName, conditionIndex ))
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
            # 종목명은 determine buy 할시 확인하므로 꼭 넣어주어야 함 
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
                if ( code not in ETF_LIST and code not in EXCEPTION_LIST):
                    self.addConditionOccurList(code)

        # 실시간 호가 정보 요청 "0" 은 이전거 제외 하고 새로 요청
        if( len(codeList) ):
           #  WARNING: 주식 시세 실시간은 리턴되지 않음!
           #    tmp = self.setRealReg(kw_util.sendRealRegSiseSrcNo, ';'.join(codeList), kw_util.type_fidset['주식시세'], "0")
           tmp = self.setRealReg(kw_util.sendRealRegHogaScrNo, ';'.join(codeList), kw_util.type_fidset['주식호가잔량'], "0")
           tmp = self.setRealReg(kw_util.sendRealRegChegyeolScrNo, ';'.join(codeList), kw_util.type_fidset['주식체결'], "0")
           tmp = self.setRealReg(kw_util.sendRealRegUpjongScrNo, '001;101', kw_util.type_fidset['업종지수'], "0")

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
    def test_etf_buy(type = 'all'):
        #etf 매수
        objKiwoom.buy_etf(type, 1)

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

    def test_etf_sell(type = 'all'):
        #etf 매도 
        objKiwoom.sell_etf(type)

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

    ui.btnStart.clicked.connect(objKiwoom.onBtnStartClicked)
    ui.btnRestart.clicked.connect(objKiwoom.onBtnRestartClicked)

    ui.btnYupjong.clicked.connect(objKiwoom.onBtnYupjongClicked)
    ui.btnJango.clicked.connect(objKiwoom.onBtnJangoClicked)
    ui.btnChegyeol.clicked.connect(objKiwoom.onBtnChegyeolClicked)
    ui.btnCondition.clicked.connect(objKiwoom.onBtnConditionClicked)

    ui.lineCmd.textChanged.connect(objKiwoom.onLineCmdTextChanged)
    ui.btnRun.clicked.connect(objKiwoom.onBtnRunClicked)

    form.show()

    sys.exit(myApp.exec_())