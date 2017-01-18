# -*-coding: utf-8 -*-
import sys, os, re, time, datetime, copy, json

import util, kw_util

from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl
from PyQt5.QtCore import QStateMachine, QState, QTimer, QFinalState
from PyQt5.QtWidgets import QApplication
from PyQt5.QtQml import QQmlApplicationEngine 
from PyQt5.QAxContainer import QAxWidget

TEST_MODE = True    # 주의 TEST_MODE 를 False 로 하는 경우, TOTAL_BUY_AMOUNT 만큼 구매하게 됨  
# AUTO_TRADING_OPERATION_TIME = [ [ [9, 10], [10, 00] ], [ [14, 20], [15, 10] ] ]  # ex) 9시 10분 부터 10시까지 14시 20분부터 15시 10분 사이에만 동작 
AUTO_TRADING_OPERATION_TIME = [ [ [9, 1], [11, 00] ], [ [14, 00], [15, 15] ] ] #해당 시스템 동작 시간 설정

# for day trading 
DAY_TRADING_ENABLE = False
DAY_TRADING_END_TIME = [15, 19] 

TRADING_INFO_GETTING_TIME = [15,35] # 트레이딩 2정보를 저장하기 시작하는 시간
STOP_LOSS_VALUE_DAY_RANGE = 4 # stoploss 의 값은 stop_loss_value_day_range 중 저가로 계산됨 ex) 10이면 10일중 저가 

CONDITION_NAME = '거래량' #키움증권 HTS 에서 설정한 조건 검색 식 이름
TOTAL_BUY_AMOUNT = 30000000 #  매도 호가1, 2 총 수량이 TOTAL_BUY_AMOUNT 이상 안되면 매수금지  (슬리피지 최소화)
#WARN: TIME_CUT_MIN = 20 # 타임컷 분값으로 해당 TIME_CUT_MIN 분 동안 가지고 있다가 시간이 지나면 손익분기점으로 손절가를 올림 # 불필요함 너무 짧은 보유 시간으로 손해 극심함  

#익절 계산하기 위해서 slappage 추가하며 이를 계산함  
SLIPPAGE = 2.0 # 기본 매수 매도시 슬리피지는 1.0 이므로 + 0.5 하고 수수료 포함하여 2.0 
STOCK_PRICE_MIN_MAX = { 'min': 2000, 'max':50000} #조건 검색식에서 오류가 가끔 발생하므로 매수 범위 가격 입력 

# 장기 보유 종목 번호 리스트 
DAY_TRADNIG_EXCEPTION_LIST = ['117930']
'''
TODO: 최대 몇종목을 동시에 보유할 것인지 결정 (보유 최대 금액과 한번 투자시 가능한 투자 금액사이의 관계를 말함) 
5개 이상 시세 과요청 오류 뜰수 있는지 체크 필요  
'''
STOCK_POSSESION_COUNT = 5 

ONE_MIN_CANDLE_EXCEL_FILE_PATH = "log" + os.path.sep + util.cur_date() + "_1min_stick.xlsx" 
CHEGYEOL_INFO_FILE_PATH = "log" + os.path.sep + util.cur_month() + "_chegyeol.json"
JANGO_INFO_FILE_PATH =  "log" + os.path.sep + util.cur_month() + "_jango.json"

class KiwoomConditon(QObject):
    sigInitOk = pyqtSignal()
    sigConnected = pyqtSignal()
    sigDisconnected = pyqtSignal()
    sigTryConnect = pyqtSignal()
    sigGetConditionCplt = pyqtSignal()
    sigSelectCondition = pyqtSignal()
    sigWaittingTrade = pyqtSignal()
    sigRefreshCondition = pyqtSignal()
    sigRequest1minTr = pyqtSignal()
    sigGetTrCplt = pyqtSignal()
    sigPrepare1minTrListComplete = pyqtSignal()
    sigStateStop = pyqtSignal()
    sigStockComplete = pyqtSignal()
    sigConditionOccur = pyqtSignal()
    sigGetBasicInfo = pyqtSignal()
    sigGetHogaInfo = pyqtSignal()
    sigBuy = pyqtSignal()
    sigNoBuy = pyqtSignal()
    sigRequestRealHogaComplete = pyqtSignal()
    sigError = pyqtSignal()
    sigRequestJangoComplete = pyqtSignal()
    sigCalculateStoplossComplete = pyqtSignal()
    sigStartProcessBuy = pyqtSignal()
    

    def __init__(self):
        super().__init__()
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.fsm = QStateMachine()
        self.qmlEngine = QQmlApplicationEngine()
        self.account_list = []
        self.timerSystem = QTimer()

        self.buyCodeList = []  # 현재 매수후 보유 종목 
        self.todayTradedCodeList = [] # 금일 거래 되었던 종목 
        self.upjongUpdownPercent= {} # 업종 등락율 


        self.jangoInfo = {} # { 'jongmokCode': { '이익실현가': 222, ...}}
        self.jangoInfoFromFile = {} # 첫매입 손절가등 데이터를 보존해야되는 데이터가 파일로 저장되어 있으며 첫 실행시 이 데이터를 로드함 
        self.chegyeolInfo = {} # { '날짜' : [ [ '주문구분', '매도', '주문/체결시간', '체결가' , '체결수량', '미체결수량'] ] }
        self.conditionOccurList = [] # 조건 진입이 발생한 모든 리스트 저장하고 매수 결정에 사용되는 모든 정보를 저장함  [ {'종목코드': code, ...}] 

        self.kospiCodeList = () 
        self.kosdaqCodeList = () 
        self.remainTimeUntilStart = '000000'

        self.createState()
        self.createConnection()
        self.currentTime = datetime.datetime.now()
        self.qmlEngine = QQmlApplicationEngine()
        
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
        waittingTradeSystemState = QState(systemState)
        standbySystemState = QState(systemState)
        requestingJangoSystemState = QState(systemState)
        calculateStoplossSystemState = QState(systemState)
        prepare1minTrListState = QState(systemState)
        request1minTrState = QState(systemState)
        
        #transition defition
        mainState.setInitialState(initState)
        mainState.addTransition(self.sigStateStop, finalState)
        mainState.addTransition(self.sigStockComplete, stockCompleteState)
        stockCompleteState.addTransition(self.sigStateStop, finalState)
        initState.addTransition(self.sigInitOk, disconnectedState)
        disconnectedState.addTransition(self.sigConnected, connectedState)
        disconnectedState.addTransition(self.sigTryConnect,  disconnectedState)
        connectedState.addTransition(self.sigDisconnected, disconnectedState)
        
        systemState.setInitialState(initSystemState)
        initSystemState.addTransition(self.sigGetConditionCplt, waittingTradeSystemState)
        waittingTradeSystemState.addTransition(self.sigWaittingTrade, waittingTradeSystemState )
        waittingTradeSystemState.addTransition(self.sigSelectCondition, requestingJangoSystemState)
        requestingJangoSystemState.addTransition(self.sigRequestJangoComplete, calculateStoplossSystemState)
        calculateStoplossSystemState.addTransition(self.sigCalculateStoplossComplete, standbySystemState)
        standbySystemState.addTransition(self.sigRefreshCondition, initSystemState)
        standbySystemState.addTransition(self.sigRequest1minTr,prepare1minTrListState ) 
        prepare1minTrListState.addTransition(self.sigPrepare1minTrListComplete, request1minTrState) 
        request1minTrState.addTransition(self.sigGetTrCplt, request1minTrState) 
        
        #state entered slot connect
        mainState.entered.connect(self.mainStateEntered)
        stockCompleteState.entered.connect(self.stockCompleteStateEntered)
        initState.entered.connect(self.initStateEntered)
        disconnectedState.entered.connect(self.disconnectedStateEntered)
        connectedState.entered.connect(self.connectedStateEntered)
        
        systemState.entered.connect(self.systemStateEntered)
        initSystemState.entered.connect(self.initSystemStateEntered)
        waittingTradeSystemState.entered.connect(self.waittingTradeSystemStateEntered)
        requestingJangoSystemState.entered.connect(self.requestingJangoSystemStateEntered)
        calculateStoplossSystemState.entered.connect(self.calculateStoplossPlusStateEntered)
        standbySystemState.entered.connect(self.standbySystemStateEntered)
        prepare1minTrListState.entered.connect(self.prepare1minTrListStateEntered)
        request1minTrState.entered.connect(self.request1minTrStateEntered)        
    
        # processBuy definition
        processBuyState = QState(connectedState)
        initProcessBuyState = QState(processBuyState)
        standbyProcessBuyState = QState(processBuyState)
        requestBasicInfoProcessBuyState = QState(processBuyState)
        requestHogaInfoProcessBuyState = QState(processBuyState)
        determineBuyProcessBuyState = QState(processBuyState)
        requestingJangoProcessBuyState = QState(processBuyState)
        calculateStoplossProcessBuyState = QState(processBuyState)
        
        processBuyState.setInitialState(initProcessBuyState)
        initProcessBuyState.addTransition(self.sigStartProcessBuy, standbyProcessBuyState)
        standbyProcessBuyState.addTransition(self.sigConditionOccur, requestBasicInfoProcessBuyState)
        requestBasicInfoProcessBuyState.addTransition(self.sigGetBasicInfo, requestHogaInfoProcessBuyState)
        requestBasicInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState )

        requestHogaInfoProcessBuyState.addTransition(self.sigGetHogaInfo, determineBuyProcessBuyState)
        requestHogaInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState)

        determineBuyProcessBuyState.addTransition(self.sigNoBuy, standbyProcessBuyState)
        determineBuyProcessBuyState.addTransition(self.sigBuy, requestingJangoProcessBuyState)

        requestingJangoProcessBuyState.addTransition(self.sigRequestJangoComplete, calculateStoplossProcessBuyState)

        calculateStoplossProcessBuyState.addTransition(self.sigCalculateStoplossComplete, standbyProcessBuyState)
        
        processBuyState.entered.connect(self.processBuyStateEntered)
        initProcessBuyState.entered.connect(self.initProcessBuyStateEntered)
        standbyProcessBuyState.entered.connect(self.standbyProcessBuyStateEntered)
        requestBasicInfoProcessBuyState.entered.connect(self.requestBasicInfoProcessBuyStateEntered)
        requestHogaInfoProcessBuyState.entered.connect(self.requestHogaInfoProcessBuyStateEntered)
        determineBuyProcessBuyState.entered.connect(self.determineBuyProcessBuyStateEntered)
        requestingJangoProcessBuyState.entered.connect(self.requestingJangoSystemStateEntered)
        calculateStoplossProcessBuyState.entered.connect(self.calculateStoplossPlusStateEntered)
                
        #fsm start
        finalState.entered.connect(self.finalStateEntered)
        self.fsm.start()

    def initQmlEngine(self):

        self.qmlEngine.addImportPath("qml")
        self.qmlEngine.load(QUrl('qml/main.qml'))        

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
    def onStartClicked(self):
        print(util.whoami())
        self.sigInitOk.emit()
        
    @pyqtSlot()
    def onRestartClicked(self):
        print(util.whoami())

    @pyqtSlot()
    def onRequestJangoClicked(self):
        self.printStockInfo()

    @pyqtSlot()
    def onChegyeolClicked(self):
        self.printChegyeolInfo('all')


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

    def isTradeAvailable(self, jongmokCode):
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
        self.save1minCandleStickInfo()
        self.sigStateStop.emit()
        pass

    def save1minCandleStickInfo(self):
        # writer = pd.ExcelWriter(ONE_MIN_CANDLE_EXCEL_FILE_PATH, engine='xlsxwriter')
        # tempDf = None 
        # sheetName = None
        # jongmokName = None
        # for jongmokCode, df in self.df1minCandleStickList.items():
        #     jongmokName = self.getMasterCodeName(jongmokCode)
        #     # 종목 이름을 sheet name 으로 해서 1분봉 데이터 저장 
        #     if( jongmokName != ""):
        #         tempDf = df.sort_values(by=['체결시간'])
        #         sheetName = jongmokName
        #     else:
        #         continue
        #     tempDf.to_excel(writer, sheet_name=sheetName )
        # writer.save()
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
                        self.todayTradedCodeList.append(parse_str_list[kw_util.dict_jusik['체결정보'].index('종목코드')])
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
    def waittingTradeSystemStateEntered(self):
        # 장시작 10분전에 조건이 시작하도록 함 
        time_span = datetime.timedelta(minutes = 20)
        expected_time = (self.currentTime + time_span).time()
        if( expected_time >= datetime.time(*AUTO_TRADING_OPERATION_TIME[0][0]) ):
            self.initQmlEngine()
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
            QTimer.singleShot(1000, self.sigWaittingTrade)

        pass

    @pyqtSlot()
    def requestingJangoSystemStateEntered(self):
        print(util.whoami() )
        self.requestOpw00018(self.account_list[0])
        pass 
    
    @pyqtSlot()
    def calculateStoplossPlusStateEntered(self):
        print(util.whoami() )
        def requestFunc(jongmokCode):
            def inner():
                self.requestOpt10081(jongmokCode)
            return inner
        request_jongmok_codes = []
        for jongmok_code in self.jangoInfo.keys():
            jango_info = self.jangoInfo[jongmok_code]
            if( '손절가' not in jango_info.keys() ):
                request_jongmok_codes.append( jongmok_code )

        if( len(request_jongmok_codes) == 0 ):
            self.sigCalculateStoplossComplete.emit()
        else:
            # 요청은 1초에 5개뿐이므로 200 ms 나눠서 함 너무 200 딱맞추면 오류 나므로 여유 줌  
            for index, jongmok_code in enumerate(request_jongmok_codes):
                func = requestFunc(jongmok_code) 
                QTimer.singleShot(220 * (index + 1), func)
            pass

    @pyqtSlot()
    def standbySystemStateEntered(self):
        print(util.whoami() )
        jango_list = self.jangoInfo.keys()
        # 잔고 리스트 추가 및 잔고리스트의 실시간 체결 정보를 받도록 함 
        for jongmokCode in jango_list:
            self.insertBuyCodeList(jongmokCode) 
        self.refreshRealRequest()
        self.sigStartProcessBuy.emit()
        pass


    @pyqtSlot()
    def prepare1minTrListStateEntered(self):
        print(util.whoami() )
        # TODO: 조건 진입 정보를 통해 1분봉 데이터 요청하기 
        # 조건 진입 정보를 읽어 종목 코드 값을 빼낸 뒤 tr 요청 
        self.sigPrepare1minTrListComplete.emit()

    @pyqtSlot()
    def request1minTrStateEntered(self):
        print(util.whoami() )
        self.sigStockComplete.emit()
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
        print(util.whoami())
        pass

    @pyqtSlot()
    def requestBasicInfoProcessBuyStateEntered(self):
        # print(util.whoami())
        if( len(self.conditionOccurList )):
            jongmokInfo_dict = self.conditionOccurList[0]
            code = jongmokInfo_dict['종목코드']
            if( self.requestOpt10001(code) == False ):
                self.sigError.emit()
        else:
            self.sigError.emit()
        pass

    @pyqtSlot()
    def requestHogaInfoProcessBuyStateEntered(self):
        # print(util.whoami())
        if( len(self.conditionOccurList )):
            jongmokInfo_dict = self.conditionOccurList[0]
            code = jongmokInfo_dict['종목코드']
            if( self.requestOpt10004(code) == False ):  
                self.sigError.emit()
        else:
            self.sigError.emit()
        pass

    @pyqtSlot()
    def determineBuyProcessBuyStateEntered(self):
        print('!')
        jongmokInfo_dict = []
        return_vals = []
        printLog = ''

        if( len(self.conditionOccurList )):
            jongmokInfo_dict = self.conditionOccurList[0]
        else:
            printLog += '(조건리스트없음)'
            return_vals.append(False)
            return
        
        # TODO: condition 발생 리스트를 따로 저장하여 1분봉 정보를 엑셀에 저장할수 있도록 함 
        self.conditionOccurList.remove(jongmokInfo_dict)
            
        jongmokName = jongmokInfo_dict['종목명']
        jongmokCode = jongmokInfo_dict['종목코드']
        # print(jongmokInfo_dict)

        printLog += ' ' + jongmokName + ' '  + jongmokCode + ' '

        if( jongmokCode in DAY_TRADNIG_EXCEPTION_LIST ):
            printLog += "(장기보유종목)"
            return_vals.append(False)

        # 최대 보유 할 수 있는 종목 보유수를 넘었는지 확인 
        if( len(self.buyCodeList) < STOCK_POSSESION_COUNT ):
            pass
        else:
            printLog += "(종목최대보유중)"
            return_vals.append(False)

        if( self.isTradeAvailable(jongmokCode) ):  
            pass
        else:
            printLog += "(거래시간X)"
            return_vals.append(False)
            
        # 호가 정보는 문자열로 기준가 대비 + , - 값이 붙어 나옴 
        maedoHoga1 =  abs(int(jongmokInfo_dict['매도최우선호가']))
        maedoHogaAmount1 =  int(jongmokInfo_dict['매도최우선잔량'])
        maedoHoga2 =  abs(int(jongmokInfo_dict['매도2차선호가']) )
        maedoHogaAmount2 =  int(jongmokInfo_dict['매도2차선잔량']) 
        #    print( util.whoami() +  maedoHoga1 + " " + maedoHogaAmount1 + " " + maedoHoga2 + " " + maedoHogaAmount2 )
        # totalAmount =  maedoHoga1 * maedoHogaAmount1  
        totalAmount = maedoHoga1 * maedoHogaAmount1 + maedoHoga2 * maedoHogaAmount2
        # print( util.whoami() + jongmokName + " " + str(sum) + (" won") ) 
        # util.save_log( '{0:^20} 호가1:{1:>8}, 잔량1:{2:>8} / 호가2:{3:>8}, 잔량2:{4:>8}'
                # .format(jongmokName, maedoHoga1, maedoHogaAmount1, maedoHoga2, maedoHogaAmount2), '호가잔량' , folder= "log") 

        # 이미 보유한 종목 구매 금지 
        if( self.buyCodeList.count(jongmokCode) == 0 ):
            pass
        else:
            printLog += '(____기보유종목____: {0})'.format(jongmokName)
            return_vals.append(False)
            pass

        # 가격조건 확인 
        if( maedoHoga1 >= STOCK_PRICE_MIN_MAX['min'] and maedoHoga1 <= STOCK_PRICE_MIN_MAX['max']):
            pass
        else:
            printLog += '(종목가격미충족: 매도호가1 {0})'.format(maedoHoga1)
            return_vals.append(False)

        # 호가 잔량이 살만큼 있는 경우  
        if( totalAmount >= TOTAL_BUY_AMOUNT):
            pass 
        else:
            printLog += '(호가수량부족: 매도호가1 {0} 매도호가잔량1 {1})'.format(maedoHoga1, maedoHogaAmount1)
            return_vals.append(False)
    
        # 가격이 많이 오르지 않은 경우 앞에 +, - 붙는 소수이므로 float 으로 먼저 처리 
        updown_percentage = float(jongmokInfo_dict['등락율'] )
        
        # 너무 급등한 종목은 사지 않도록 함 
        if( updown_percentage > 0 and updown_percentage < 30 - 15 ):
            pass
        else:
            printLog += '(종목등락율미충족: 등락율{0})'.format(updown_percentage)
            return_vals.append(False)

        # 업종 등락율을 살펴서 마이너스 이면 사지 않음 :
        if( jongmokCode in  self.kospiCodeList):
            updown_percentage = float(self.upjongUpdownPercent.get('코스피', -99) )
            if( updown_percentage < 0 ) :
                printLog +='(코스피등락율미충족: 등락율{0})'.format(updown_percentage)
                return_vals.append(False)
            pass
        else: 
            updown_percentage = float(self.upjongUpdownPercent.get('코스닥', -99) )
            if( updown_percentage < 0 ) :
                printLog +='(코스닥등락율미충족: 등락율{0})'.format(updown_percentage)
                return_vals.append(False)

        # 저가가 전일종가 밑으로 내려간적 있는 지 확인 
        # low_price = int(jongmokInfo_dict['저가'])
        # if( low_price >= base_price ):
        #     pass
        # else:
        #     printLog += '(저가가전일종가보다낮음)'
        #     return_vals.append(False)

        # 기존에 이미 수익이 한번 발생한 종목이라면  
        if( self.todayTradedCodeList.count(jongmokCode) == 0 ):
            pass
        else:
            printLog += '(금일거래종목)'
            return_vals.append(False)

        # 매수 
        if( return_vals.count(False) == 0 ):
            util.save_log(jongmokName, '매수주문', folder= "log")
            maesu_count = 0 
            if( TEST_MODE == True ):
                maesu_count = 1
            else:
                maesu_count = round((TOTAL_BUY_AMOUNT / maedoHogaAmount2) - 0.5) # 첫번째 자리수 버림

            result = self.sendOrder("buy_" + jongmokCode, kw_util.sendOrderScreenNo, 
                                objKiwoom.account_list[0], kw_util.dict_order["신규매수"], jongmokCode, 
                                maesu_count, 0 , kw_util.dict_order["시장가"], "")
            print("B " + str(result) , sep="")
            pass
        else:
            util.save_log(printLog, '조건진입매수실패', folder = "log")
            self.refreshRealRequest()
            self.sigNoBuy.emit()
        pass
     
    @pyqtSlot()
    def finalStateEntered(self):
        print(util.whoami())
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
    # 주식 기본정보 요청 
    def requestOpt10001(self, jongmokCode):
        self.setInputValue("종목코드", jongmokCode) 
        ret = self.commRqData(jongmokCode, "opt10001", 0, kw_util.sendJusikGibonScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString = jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True
    
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
        

    # 주식 호가 잔량 요청
    def requestOpt10004(self, jongmokCode):
        self.setInputValue("종목코드", jongmokCode) 
        ret = self.commRqData(jongmokCode, "opt10004", 0, kw_util.sendJusikHogaScreenNo) 
        
        errorString = None
        if( ret != 0 ):
            errorString =   jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
            return False
        return True

    # 1분봉 tr 요청 
    def requestOpt10080(self, jongmokCode):
     # 분봉 tr 요청의 경우 너무 많은 데이터를 요청하므로 한개씩 수행 
        self.setInputValue("종목코드", jongmokCode )
        self.setInputValue("틱범위","1:1분") 
        self.setInputValue("수정주가구분","0") 
        # rQName 을 데이터로 외부에서 사용
        ret = self.commRqData(jongmokCode , "opt10080", 0, kw_util.send1minTrScreenNo) 
        
        errorString = None
        if( ret != 0 ):
            errorString =  self.getMasterCodeName(jongmokCode) + " commRqData() " + kw_util.parseErrorCode(str(ret))
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
            
            # 장기 보유종목인 경우 제외 
            if( jongmokCode not in DAY_TRADNIG_EXCEPTION_LIST):
                if( jongmokCode not in self.jangoInfo.keys() ):
                    self.jangoInfo[jongmokCode] = info_dict
                else:
                    # 기존에 가지고 있는 종목이면 update
                    self.jangoInfo[jongmokCode].update(info_dict)

        # print(self.jangoInfo)
        return True 

    # 주식 일봉 정보를 통해 손절가와 이익실현가를 계산함 
    def makeOpt10081Info(self, rQName):
        repeatCnt = self.getRepeatCnt("opt10081", rQName)
        jongmok_code = rQName
        price_list = [] # 몇봉중 저가, 고가 를 뽑아내기 위함?
        info_dict = self.jangoInfo[jongmok_code]

        for i in range(repeatCnt):
            line = {} 
            for item_name in kw_util.dict_jusik['TR:일봉']:
                if( item_name == "종목명" ):
                    line[item_name] = self.getMasterCodeName(rQName)
                    continue
                result = self.getCommData("opt10081", rQName, i, item_name)
                line[item_name] = result.strip()

            # 일자가 맨 마지막 리스트 
            saved_date_str = line['일자']
            time_span = datetime.timedelta(days = STOP_LOSS_VALUE_DAY_RANGE) # 몇일 중  저가 계산
            saved_date = datetime.datetime.strptime(saved_date_str, '%Y%m%d').date()
            current_date = self.currentTime.date()
            price_list.append(int(line['저가']))
            if( saved_date <  current_date - time_span):
                break
        
        # 손절가는 몇일전 저가 에서 정하고 시간이 지나갈수록 올라가는 형태여야 함 
        info_dict['손절가'] = min(price_list)

        # 첫매입시 손절가 정보는 잔고 정보 파일에 위치함
        # 첫 매수시 설정했던 손절가 설정 없으면 몇일중 최저가에서 설정함  
        first_stoploss = sys.maxsize

        if( jongmok_code in self.jangoInfoFromFile ):
            # 매입가를 비교하는 이유는 서버 데이터와 파일 데이터가 날짜가 일치 하는지 확인하기 위한 편법 
            if( self.jangoInfoFromFile[jongmok_code]['매입가'] == self.jangoInfo[jongmok_code]['매입가'] ):
                first_stoploss = self.jangoInfoFromFile[jongmok_code]['첫매입손절가']

        price_list.append(first_stoploss)
        first_stoploss = min(price_list)
        # 첫 매수시 체결정보에도 첫매입 손절가를 입력해줌 
        info_dict['첫매입손절가'] = first_stoploss
        maeip_price = info_dict['매입가']

        # 가격 변화량에 따라 이익실현가를 달리하기 위함 첫 매입과 매입가의 폭에서 2/3 하고 슬리피지 더한값을 이익실현으로 잡음 
        info_dict['이익실현가'] = maeip_price * ( 1 + (((maeip_price - first_stoploss ) / maeip_price) * 2 / 3) + SLIPPAGE / 100)

        # print(util.whoami() + ' ' +  info_dict['종목명'], price_list, min(price_list))
        return True
        pass
    # 주식 기본 정보 
    def makeOpt10001Info(self, rQName):
        if( len(self.conditionOccurList) ):
            jongmokInfo_dict = self.conditionOccurList[0]
        else:
            return False

        for item_name in kw_util.dict_jusik['TR:주식기본정보']:
            result = self.getCommData("opt10001", rQName, 0, item_name)
            jongmokInfo_dict[item_name] = result.strip()

        # print(df)
        return True
        pass

    #주식 호가 정보 
    def makeOpt10004Info(self, rQName):
        if( len(self.conditionOccurList) ):
            jongmokInfo_dict = self.conditionOccurList[0]
        else:
            return False
        for item_name in kw_util.dict_jusik['TR:주식호가요청']:
            result = self.getCommData("opt10004", rQName, 0, item_name)
            jongmokInfo_dict[item_name] = result.strip()
        # print(jongmokInfo_dict)
        return True
        pass
    
            
    # 1분봉 데이터 생성 
    def makeOpt10080Info(self, rQName):
        repeatCnt = self.getRepeatCnt("opt10080", rQName)
        currentTimeStr  = None 
        for i in range(repeatCnt):
            line = []
            for item_name in kw_util.dict_jusik['TR:분봉']:
                if( item_name == "종목명" ):
                    line.append(self.getMasterCodeName(rQName))
                    continue
                result = self.getCommData("opt10080", rQName, i, item_name)
                if( item_name == "체결시간"):
                    currentTimeStr = result.strip()
                line.append(result.strip())

            # print(line)
            # 오늘 이전 데이터는 받지 않는다
            resultTime = time.strptime(currentTimeStr,  "%Y%m%d%H%M%S")
            currentTime = time.localtime()
            if( resultTime.tm_mday == currentTime.tm_mday ):
                pass
                # 기존에 저장되어 있는 않는 데이터만 저장하고 이미 데이터가 있는 경우 리턴한다. 
                # try:
                #     df = self.df1minCandleStickList[rQName]
                #     # any 를 해야 dataframe 이 리턴되지 않고 True, False 로 리턴됨 
                #     if((df['체결시간'] == currentTimeStr).any() ):
                #         #중복 나올시 바로 나옴 
                #         break
                #     else:
                #         # print(line)
                #         df.loc[df.shape[0]] = line 
                # except KeyError:
                #     self.df1minCandleStickList[rQName] = pd.DataFrame(columns = kw_util.dict_jusik['TR:분봉'])
                #     df = self.df1minCandleStickList[rQName]
                #     df.loc[df.shape[0]] = line
                #     # print(line)
            else:
                break

    @pyqtSlot()
    def onTimerSystemTimeout(self):
        print(".", end='') 
        self.currentTime = datetime.datetime.now()

        if( self.getConnectState() != 1 ):
            util.save_log("Disconnected!", "시스템", folder = "log")
            self.sigDisconnected.emit() 
        else:
            if( datetime.time(*TRADING_INFO_GETTING_TIME) <=  self.currentTime.time() ): 
                self.timerSystem.stop()
                util.save_log("Stock Trade Terminate!", "시스템", folder = "log")
                self.sigRequest1minTr.emit()
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
        '''
              [OnReceiveTrData() 이벤트함수]
          
          void OnReceiveTrData(
          BSTR sScrNo,       // 화면번호
          BSTR sRQName,      // 사용자 구분명
          BSTR sTrCode,      // TR이름
          BSTR sRecordName,  // 레코드 이름
          BSTR sPrevNext,    // 연속조회 유무를 판단하는 값 0: 연속(추가조회)데이터 없음, 1:연속(추가조회) 데이터 있음
          LONG nDataLength,  // 사용안함.
          BSTR sErrorCode,   // 사용안함.
          BSTR sMessage,     // 사용안함.
          BSTR sSplmMsg     // 사용안함.
          )
          
          조회요청 응답을 받거나 조회데이터를 수신했을때 호출됩니다.
          조회데이터는 이 이벤트 함수내부에서 GetCommData()함수를 이용해서 얻어올 수 있습니다.
        '''
        printData =  'sScrNo: {}, sRQName: {}, sTrCode: {}, sMsg: {}'.format(scrNo, rQName, trCode, msg)
        util.save_log(printData, "시스템메시지", "log")
        pass

    # Tran 수신시 이벤트
    def _OnReceiveTrData(   self, scrNo, rQName, trCode, recordName,
                            prevNext, dataLength, errorCode, message,
                            splmMsg):
        print('')
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
                ret_vals = []
                for jangoInfo in self.jangoInfo.values():
                    if( '손절가' not in jangoInfo.keys() ):
                        ret_vals.append(False)
                if( ret_vals.count(False) == 0 ):
                    self.printStockInfo()
                    self.sigCalculateStoplossComplete.emit()
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
        elif( trCode == "opt10004"):
            if( self.makeOpt10004Info(rQName) ):
                self.sigGetHogaInfo.emit()
            else:
                self.sigError.emit()
            pass
        # 주식 분봉 
        elif( trCode == "opt10080"):     
            self.makeOpt10080Info(rQName)
            if( rQName in self.oneMinCandleJongmokList):
                self.oneMinCandleJongmokList.remove(rQName)
                QTimer.singleShot(200, self.sigGetTrCplt)
            pass


    # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmokCode, realType, realData):
        # print(util.whoami() + 'jongmokCode: {}, {}, realType: {}'
        #         .format(jongmokCode, self.getMasterCodeName(jongmokCode),  realType))
        if( realType == "주식호가잔량"):
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))
            if( self.buyCodeList.count(jongmokCode) == 0 ):
                jongmokName = self.getMasterCodeName(jongmokCode) 
                print(util.whoami() + 'error: ' + jongmokCode + ' ' + jongmokName, end =' ')
            self.makeHogaJanRyangInfo(jongmokCode)                

        if( realType == "주식체결"):
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))
            self.processStopLoss(jongmokCode)
        
        if( realType == "업종지수" ):
            result = '' 
            for col_name in kw_util.dict_jusik['실시간-업종지수']:
                result = self.getCommRealData(jongmokCode, kw_util.name_fid[col_name] ) 
                if( col_name == '등락율'):
                    if( jongmokCode == '001'):
                        self.upjongUpdownPercent['코스피'] = result
                    else:
                        self.upjongUpdownPercent['코스닥'] = result 
            pass 
        
        if( realType == '장시작시간'):
            pass
            # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
            #     .format(jongmokCode, realType, realData))

    # 실시간 호가 잔량 정보         
    def makeHogaJanRyangInfo(self, jongmokCode):
        #주식 호가 잔량 정보 요청 
        result = None 
        for col_name in kw_util.dict_jusik['실시간-주식호가잔량']:
            result = self.getCommRealData(jongmokCode, kw_util.name_fid[col_name] ) 
            if( jongmokCode not in self.jangoInfo):
                break
            self.jangoInfo[jongmokCode][col_name] = result.strip()
        pass 


    def processStopLoss(self, jongmokCode):
        jongmokName = self.getMasterCodeName(jongmokCode)
        # 잔고에 없는 종목이면 종료 
        if( jongmokCode not in self.jangoInfo.keys() ):
            return 
        current_jango = self.jangoInfo[jongmokCode]

        jangosuryang = int( current_jango['매매가능수량'] )
        stop_loss, stop_plus = 0,0

        # after buy command, before stoploss calculate this routine can run 
        if( '손절가' not in current_jango or '매수호가1' not in current_jango):
            return

        # 손절가는 매수시 기준가(전일종가)로 책정되어 있음 
        stop_loss = int(current_jango['손절가'])
        stop_plus = int(current_jango['이익실현가'])
        maeipga = int(current_jango['매입가'])

        # day trading 주식 거래 시간 종료가 가까운 경우 모든 종목 매도 
        if( DAY_TRADING_ENABLE == True ):
            if( datetime.time(*DAY_TRADING_END_TIME) <  self.currentTime.time() ):
                # 바로 매도 해야 하므로 큰 값을 넣도록 함 
                stop_loss = int(current_jango['매입가'] ) * 100

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

        if( stop_loss >= maesuHoga1 ) :
            printData += "(손절)"
            isSell = True
        if( stop_plus < maesuHoga1 ) :
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
                        ' 매수호가1 {0:7}/'.format(str(maesuHoga1)) + \
                        ' 매수호가수량1 {0:7}/'.format(str(maesuHogaAmount1)) + \
                        ' 매수호가2 {0:7}/'.format(str(maesuHoga2)) + \
                        ' 매수호가수량2 {0:7}/'.format(str(maesuHogaAmount2)) 

        if( isSell == True ):
            result = self.sendOrder("sell_"  + jongmokCode, kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
                                jongmokCode, jangosuryang, 0 , kw_util.dict_order["시장가"], "")
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
            boyouSuryang = int(self.getChejanData(930))
            self.todayTradedCodeList.append(jongmok_code)
            if( boyouSuryang == 0 ):
                self.removeBuyCodeList(jongmok_code)
                self.makeJangoInfoFile()
            else:
                # 보유 수량이 늘었다는 것은 매수수행했다는 소리임 
                # BuyCode List 에 넣지 않으면 호가 정보가 빠르게 올라오는 경우 계속 매수됨   
                # 매수시 체결 정보의 경우는 매수 기본 손절가 측정시 계산됨 
                self.insertBuyCodeList(jongmok_code)
                self.makeJangoInfoFile()
                self.sigBuy.emit()
            pass

        elif ( gubun == "0"):
            jumun_sangtae =  self.getChejanData(913)
            jongmok_code = self.getChejanData(9001)[1:]
            if( jumun_sangtae == "체결"):
                self.makeChegyeolInfo(jongmok_code, fidList)
                self.makeChegyeolInfoFile()
                pass
            pass

    def makeChegyeolInfoFile(self):
        print(util.whoami())
        with open(CHEGYEOL_INFO_FILE_PATH, 'w', encoding = 'utf8' ) as f:
            f.write(json.dumps(self.chegyeolInfo, ensure_ascii= False, indent= 2, sort_keys = True ))
        pass

    def makeJangoInfoFile(self):
        print(util.whoami())
        remove_keys = [ '매도호가1','매도호가2', '매도호가수량1', '매도호가수량2', '매도호가촐잔량',
                        '매수호가1', '매수호가2', '매수호가수량1', '매수호가수량2', '매수호가총잔량',
                        '현재가', '호가시간', '세금', '전일종가', '현재가', '종목번호' ]
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
    
        current_date = self.currentTime.date().strftime("%y%m%d")

        if( current_date not in self.chegyeolInfo) :
            self.chegyeolInfo[current_date] = [] 

        self.chegyeolInfo[current_date].append('|'.join(info))
        util.save_log(printData, "*체결정보", folder= "log")
        pass

    def insertBuyCodeList(self, jongmok_code):
        if( jongmok_code not in self.buyCodeList ):
            self.buyCodeList.append(jongmok_code)
            self.refreshRealRequest()
        pass

    #주식 호가 잔량 정보 요청리스트 삭제 
    def removeBuyCodeList(self, jongmok_code):
        if( jongmok_code in self.buyCodeList ):
            self.buyCodeList.remove(jongmok_code)
        self.refreshRealRequest()
        # 잔고 정보 삭제 
        self.jangoInfo.pop(jongmok_code)
        pass

    def insertSellCodeList(self, jongmok_code):
        if( jongmok_code not in self.sellCodeList ):
            self.sellCodeList.append(jongmok_code)
        pass
    
    def removeSellCodeList(self, jongmok_code):
        if( jongmok_code in self.sellCodeList ):
            self.buyCodeList.remove(jongmok_code)
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
            print('code: {} '.format(code) + self.getMasterCodeName(code))

    # 편입, 이탈 종목이 실시간으로 들어옵니다.
    # strCode : 종목코드
    # strType : 편입(“I”), 이탈(“D”)
    # strConditionName : 조건명
    # strConditionIndex : 조건명 인덱스
    def _OnReceiveRealCondition(self, code, type, conditionName, conditionIndex):
        # print(util.whoami() + 'code: {}, type: {}, conditionName: {}, conditionIndex: {}'
        # .format(code, type, conditionName, conditionIndex ))
        typeName = ''
        if type == 'I':
            typeName = '진입'
        else:
            typeName = '이탈'

        if( typeName == '진입'):
            printLog = '{}, status: {}'.format( self.getMasterCodeName(code), typeName)
            self.makeConditionOccurInfo(code) # 조건 발생한 경우 무조건 df 저장
            self.sigConditionOccur.emit()
        pass 

    def makeConditionOccurInfo(self, jongmok_code):

        #발생시간, 종목코드,  종목명
        time = util.cur_date_time()
        jongmok_name = self.getMasterCodeName(jongmok_code)
        self.conditionOccurList.append( {'발생시간': time, '종목이름': jongmok_name, '종목코드': jongmok_code} )
        pass

     # 실시간  주식 정보 요청 요청리스트 갱신  
    def refreshRealRequest(self):
        # 버그로 모두 지우고 새로 등록하게 함 
        self.setRealRemove("ALL", "ALL")
        codeList  = []
        for code in self.buyCodeList:
            codeList.append(code)
        # 실시간 호가 정보 요청 "0" 은 이전거 제외 하고 새로 요청
        if( len(codeList) ):
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
    # putenv 는 current process 에 영향을 못끼치므로 environ 에서 직접 세팅 
    # qml debugging 를 위해 QML_IMPORT_TRACE 환경변수 1로 세팅 후 DebugView 에서 디버깅 메시지 확인 가능  
    os.environ['QML_IMPORT_TRACE'] = '1'
    # print(os.environ['QML_IMPORT_TRACE'])
    myApp = QApplication(sys.argv)
    objKiwoom = KiwoomConditon()

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
        objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
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
        objKiwoom.conditionOccurList.append({'종목코드': '044180'}) 
        objKiwoom.sigConditionOccur.emit()
        pass
    def test_make_jangoInfo():
        objKiwoom.makeJangoInfoFile()
        pass
    def test_make_chegyeolInfo():
        objKiwoom.makeChegyeolInfoFile()
        pass
    sys.exit(myApp.exec_())


