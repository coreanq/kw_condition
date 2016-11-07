# -*-coding: utf-8 -*-
import sys, os, re, time, datetime, math

import pandasmodel
import util 
import kw_util  
import pandas as pd

from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl
from PyQt5.QtCore import QStateMachine, QState, QTimer, QFinalState
from PyQt5.QtWidgets import QApplication
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QAxContainer import QAxWidget

TEST_MODE = True    # 주의 TEST_MODE 를 False 로 하는 경우, TOTAL_BUY_AMOUNT 만큼 구매하게 됨  
# AUTO_TRADING_OPERATION_TIME = [ [ [9, 10], [10, 00] ], [ [14, 20], [15, 10] ] ]  # ex) 9시 10분 부터 10시까지 14시 20분부터 15시 10분 사이에만 동작 
AUTO_TRADING_OPERATION_TIME = [ [ [9, 1], [15, 10] ]] #해당 시스템 동작 시간 설정 -->  9시 5분 부터 15시 10분까지만 동작
AUTO_TRADING_END_TIME = [15, 10] 
TRADING_INFO_GETTING_TIME = [15,40] # 트레이딩 정보를 저장하기 시작하는 시간 

CONDITION_NAME = '거래량' #키움증권 HTS 에서 설정한 조건 검색 식 이름
TOTAL_BUY_AMOUNT = 30000000 #  매도 호가1 총 수량이 TOTAL_BUY_AMOUNT 이상 안되면 매수금지  (슬리피지 최소화)
# TIME_CUT_MIN = 20 # 타임컷 분값으로 해당 TIME_CUT_MIN 분 동안 가지고 있다가 시간이 지나면 손익분기점으로 손절가를 올림 # 불필요함 너무 짧은 보유 시간으로 손해 극심함  
STOP_PLUS_PERCENT = 4 # 익절 퍼센티지 # 손절은 자동으로 기준가로 정해지고 매수시 기준가 + STOP_PLUS_PERCENT 이상이 아니면 매수하지 않음  
STOCK_PRICE_MIN_MAX = { 'min': 2000, 'max':50000} #조건 검색식에서 오류가 가끔 발생하므로 매수 범위 가격 입력 
STOCK_POSSESION_COUNT = 5 # 최대 몇종목을 동시에 보유할 것인지 결정 (보유 최대 금액과 한번 투자시 가능한 투자 금액사이의 관계를 말함) 하루에 기회가 많지 않으므로 5개 이상 금지 


ONE_MIN_CANDLE_EXCEL_FILE_PATH = "log" + os.path.sep + util.cur_date() + "_1min_stick.xlsx" 
STOCK_INFO_EXCEL_FILE_PATH = "log" + os.path.sep + util.cur_date() +"_stock.xlsx"

class KiwoomConditon(QObject):
    sigInitOk = pyqtSignal()
    sigConnected = pyqtSignal()
    sigDisconnected = pyqtSignal()
    sigTryConnect = pyqtSignal()
    sigGetConditionCplt = pyqtSignal()
    sigSelectCondition = pyqtSignal()
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
    

    def __init__(self):
        super().__init__()
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.fsm = QStateMachine()
        self.qmlEngine = QQmlApplicationEngine()
        self.account_list = []
        self.timerSystem = QTimer()
        self.buyCodeList = []
        self.conditionOccurList = [] # 조건 진입이 발생한 모든 리스트 저장 분봉 저장용으로 사용 
        self.modelCondition = pandasmodel.PandasModel(pd.DataFrame(columns = ('조건번호', '조건명')))
        # 종목번호를 key 로 하여 pandas dataframe 을 value 로 함 
        self.df1minCandleStickList = {}
        self.dfStockInfoList ={}
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
        waitingSelectSystemState = QState(systemState)
        standbySystemState = QState(systemState)
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
        initSystemState.addTransition(self.sigGetConditionCplt, waitingSelectSystemState)
        waitingSelectSystemState.addTransition(self.sigSelectCondition, standbySystemState)
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
        waitingSelectSystemState.entered.connect(self.waitingSelectSystemStateEntered)
        standbySystemState.entered.connect(self.standbySystemStateEntered)
        prepare1minTrListState.entered.connect(self.prepare1minTrListStateEntered)
        request1minTrState.entered.connect(self.request1minTrStateEntered)        
    

        # processBuy definition
        processBuyState = QState(connectedState)
        standbyProcessBuyState = QState(processBuyState)
        requestBasicInfoProcessBuyState = QState(processBuyState)
        requestHogaInfoProcessBuyState = QState(processBuyState)
        determineBuyProcessBuyState = QState(processBuyState)
        
        processBuyState.setInitialState(standbyProcessBuyState)
        standbyProcessBuyState.addTransition(self.sigConditionOccur, requestBasicInfoProcessBuyState)
        requestBasicInfoProcessBuyState.addTransition(self.sigGetBasicInfo, requestHogaInfoProcessBuyState)
        requestBasicInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState )

        requestHogaInfoProcessBuyState.addTransition(self.sigGetHogaInfo, determineBuyProcessBuyState)
        requestHogaInfoProcessBuyState.addTransition(self.sigError, standbyProcessBuyState)

        determineBuyProcessBuyState.addTransition(self.sigNoBuy, standbyProcessBuyState)
        determineBuyProcessBuyState.addTransition(self.sigBuy, standbyProcessBuyState)
        
        processBuyState.entered.connect(self.processBuyStateEntered)
        standbyProcessBuyState.entered.connect(self.standbyProcessBuyStateEntered)
        requestBasicInfoProcessBuyState.entered.connect(self.requestBasicInfoProcessBuyStateEntered)
        requestHogaInfoProcessBuyState.entered.connect(self.requestHogaInfoProcessBuyStateEntered)
        determineBuyProcessBuyState.entered.connect(self.determineBuyProcessBuyStateEntered)
                
        #fsm start
        finalState.entered.connect(self.finalStateEntered)
        self.fsm.start()

    def initQmlEngine(self):
        rootContext = self.qmlEngine.rootContext()
        rootContext.setContextProperty("cppModelCondition", self.modelCondition)
        self.qmlEngine.load(QUrl('main.qml'))
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
        for start, stop in AUTO_TRADING_OPERATION_TIME:
            start_time =  datetime.datetime( year = self.currentTime.year,
                            month = self.currentTime.month, 
                            day = self.currentTime.day, 
                            hour = start[0],
                            minute = start[1])
            stop_time =   datetime.datetime( year = self.currentTime.year,
                            month = self.currentTime.month, 
                            day = self.currentTime.day, 
                            hour = stop[0],
                            minute = stop[1])
            if( self.currentTime >= start_time and self.currentTime <= stop_time ):
                pass    
            else:
                ret_vals.append(False)

        
        if( ret_vals.count(False) ):
            return False
        else:
            return True
        pass
  
    @pyqtSlot()
    def mainStateEntered(self):
        self.loadStockInfoExcel()
        pass

    def loadStockInfoExcel(self):
        if( os.path.isfile( STOCK_INFO_EXCEL_FILE_PATH) == True):
            xls_file = pd.ExcelFile(STOCK_INFO_EXCEL_FILE_PATH)
            for sheetName in xls_file.sheet_names:
                self.dfStockInfoList[sheetName] = xls_file.parse(sheetName)
            pass

    @pyqtSlot()
    def stockCompleteStateEntered(self):
        print(util.whoami())
        self.save1minCandleStickInfo()
        self.saveStockInfo()
        self.sigStateStop.emit()
        pass

    def save1minCandleStickInfo(self):
        writer = pd.ExcelWriter(ONE_MIN_CANDLE_EXCEL_FILE_PATH, engine='xlsxwriter')
        tempDf = None 
        sheetName = None
        jongmokName = None
        for jongmokCode, df in self.df1minCandleStickList.items():
            jongmokName = self.getMasterCodeName(jongmokCode)
            # 종목 이름을 sheet name 으로 해서 1분봉 데이터 저장 
            if( jongmokName != ""):
                tempDf = df.sort_values(by=['체결시간'])
                sheetName = jongmokName
            else:
                continue
            tempDf.to_excel(writer, sheet_name=sheetName )
        writer.save()
        pass
        
    def saveStockInfo(self):
        writer = pd.ExcelWriter(STOCK_INFO_EXCEL_FILE_PATH, engine='xlsxwriter')
        for sheetName, df in self.dfStockInfoList.items():
            df.to_excel(writer, sheet_name=sheetName )
        writer.save()
        pass

    @pyqtSlot()
    def initStateEntered(self):
        # print(util.whoami())
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
        # ui 현시
        # self.initQmlEngine()
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
        # get 조건 검색 리스트
        self.getConditionLoad()
        pass

    @pyqtSlot()
    def waitingSelectSystemStateEntered(self):
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
        
        self.sigSelectCondition.emit()

        pass

    @pyqtSlot()
    def standbySystemStateEntered(self):
        print(util.whoami() )
        jangoList = [] 
        self.timerSystem.start()
        try: 
            df = self.dfStockInfoList["잔고정보"]
            for index, row in df.iterrows():
                jangoList.append(row["종목코드"]) 
                pass
        except KeyError:
            pass 
        for jongmokCode in jangoList:
            self.insertBuyCodeList(str(jongmokCode)) 
        pass

    @pyqtSlot()
    def prepare1minTrListStateEntered(self):
        print(util.whoami() )
        self.conditionOccurList = [] 
        # 조건 진입 정보를 읽어 종목 코드 값을 빼낸 뒤 tr 요청 
        try:
            df = self.dfStockInfoList['체결정보'].drop_duplicates("종목코드")
            for index, series in df.iterrows():
                self.conditionOccurList.append(series["종목코드"])
        except KeyError:
            pass  
        self.sigPrepare1minTrListComplete.emit()

    @pyqtSlot()
    def request1minTrStateEntered(self):
        print(util.whoami() )
        if( len(self.conditionOccurList) == 0 ):
            self.sigStockComplete.emit()
            return
        self.requestOpt10080(self.conditionOccurList[0])
        pass

    @pyqtSlot()
    def processBuyStateEntered(self):
        pass
     
    @pyqtSlot()
    def standbyProcessBuyStateEntered(self):
        print(util.whoami())
        pass

    @pyqtSlot()
    def requestBasicInfoProcessBuyStateEntered(self):
        print(util.whoami())
        if( len(self.conditionOccurList )):
            jongmokInfo_dict = self.conditionOccurList[0]
            self.requestOpt10001(jongmokInfo_dict['종목코드'])
        else:
            self.sigError.emit()
        pass

    @pyqtSlot()
    def requestHogaInfoProcessBuyStateEntered(self):
        print(util.whoami())
        if( len(self.conditionOccurList )):
            jongmokInfo_dict = self.conditionOccurList[0]
            code = jongmokInfo_dict['종목코드']
            self.requestOpt10004(code) 
        else:
            self.sigError.emit()
        pass

    @pyqtSlot()
    def determineBuyProcessBuyStateEntered(self):
        print(util.whoami())
        jongmokInfo_dict = []
        return_vals = []
        printLog = ''

        if( len(self.conditionOccurList )):
            jongmokInfo_dict = self.conditionOccurList[0]
        else:
            printLog += '(조건리스트없음)'
            return_vals.append(False)
            return

        self.conditionOccurList.remove(jongmokInfo_dict)
            
        jongmokName = jongmokInfo_dict['종목명']
        jongmokCode = jongmokInfo_dict['종목코드']
        print(jongmokInfo_dict)

        printLog += ' ' + jongmokName + ' '  + jongmokCode + ' '

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
        totalAmount =  maedoHoga1 * maedoHogaAmount1  
        # print( util.whoami() + jongmokName + " " + str(sum) + (" won") ) 
        # util.save_log( '{0:^20} 호가1:{1:>8}, 잔량1:{2:>8} / 호가2:{3:>8}, 잔량2:{4:>8}'
                # .format(jongmokName, maedoHoga1, maedoHogaAmount1, maedoHoga2, maedoHogaAmount2), '호가잔량' , folder= "log") 

        # 이미 보유한 종목 구매 금지 
        if( self.buyCodeList.count(jongmokCode) == 0 ):
            pass
        else:
            printLog += '( !이미보유종목! )'
            return_vals.append(False)
            pass

        # 가격조건 확인 
        if( maedoHoga1 >= STOCK_PRICE_MIN_MAX['min'] and maedoHoga1 <= STOCK_PRICE_MIN_MAX['max']):
            pass
        else:
            printLog += '(종목가격미충족)' 
            return_vals.append(False)

        # 호가 잔량이 살만큼 있는 경우  
        if( totalAmount >= TOTAL_BUY_AMOUNT):
            pass 
        else:
            printLog += '(호가수량부족)'
            return_vals.append(False)
    
        # 가격이 많이 오르지 않은 경우 앞에 +, - 붙는 소수이므로 float 으로 먼저 처리 
        updown_percentage = float(jongmokInfo_dict['등락율'] )
        
        if( updown_percentage > 0 and updown_percentage < 30 - (STOP_PLUS_PERCENT * 1.5) ):
            pass
        else:
            printLog += '(등락률미충족)'
            return_vals.append(False)

        # 기준가 + 익절 퍼센티지 미달인 경우 매수 하지 않음 
        base_price = int(jongmokInfo_dict['기준가'])
        if( maedoHoga1 >= base_price * (1 + STOP_PLUS_PERCENT / 100)):
            pass
        else:
            printLog += '(기준가미충족)'
            return_vals.append(False)
        
        # 저가가 전일종가 밑으로 내려간적 있는 지 확인 
        low_price = int(jongmokInfo_dict['저가'])
        if( low_price >= base_price ):
            pass
        else:
            printLog += '(저가가전일종가보다낮음)'
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
            # BuyCode List 에 넣지 않으면 호가 정보가 빠르게 올라오는 경우 계속 매수됨   
            self.insertBuyCodeList(jongmokCode)
            self.sigBuy.emit()
            pass
        else:
            util.save_log(printLog, '조건진입매수실패', folder = "log")
            print('remove janrynag '+ jongmokCode)
            self.removeJanRyangCodeList(jongmokCode)
            self.sigNoBuy.emit()
        pass
     
    @pyqtSlot()
    def finalStateEntered(self):
        print(util.whoami())
        pass
    
    # 주식 기본정보 요청 
    def requestOpt10001(self, jongmokCode):
        self.setInputValue("종목코드", jongmokCode) 
        ret = self.commRqData(jongmokCode, "opt10001", 0, kw_util.sendJusikGibonScreenNo) 
        errorString = None
        if( ret != 0 ):
            errorString =   jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
        pass


    # 주식 호가 잔량 요청
    def requestOpt10004(self, jongmokCode):
        self.setInputValue("종목코드", jongmokCode) 
        ret = self.commRqData(jongmokCode, "opt10004", 0, kw_util.sendJusikHogaScreenNo) 
        
        errorString = None
        if( ret != 0 ):
            errorString =   jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
        pass

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
        pass

    # 업종 현재가 요청 
    def requestOpt20003(self, yupjongCode):
        self.setInputValue("업종코드", yupjongCode) 
        ret = self.commRqData("yupjong_" +  yupjongCode , "opt20003", 0, kw_util.sendReqYupjongScreenNo) 
        
        errorString = None
        if( ret != 0 ):
            errorString =   yupjongCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
        pass

     #주식 기본 정보 
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
    
            
    # 1분봉 데이터 생성 --> to dataframe
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
                # 기존에 저장되어 있는 않는 데이터만 저장하고 이미 데이터가 있는 경우 리턴한다. 
                try:
                    df = self.df1minCandleStickList[rQName]
                    # any 를 해야 dataframe 이 리턴되지 않고 True, False 로 리턴됨 
                    if((df['체결시간'] == currentTimeStr).any() ):
                        #중복 나올시 바로 나옴 
                        break
                    else:
                        # print(line)
                        df.loc[df.shape[0]] = line 
                except KeyError:
                    self.df1minCandleStickList[rQName] = pd.DataFrame(columns = kw_util.dict_jusik['TR:분봉'])
                    df = self.df1minCandleStickList[rQName]
                    df.loc[df.shape[0]] = line
                    # print(line)
            else:
                break

    # 전업종 지수
    def makeOpt20003Info(self, rQName):
        # repeatCnt = self.getRepeatCnt("opt20003", rQName)
        # kospi 와 kosdaq 만 얻을 것이므로 몇 첫번째 데이터만 취함 
        index = 0
        line = []
        jongmokName = ""
        for item_name in kw_util.dict_jusik['TR:전업종지수']:
            result = self.getCommData("opt20003", rQName, index, item_name)
            if( item_name == '종목명'):
                jongmokName = result.strip()
            line.append(result.strip())
      # print(line)
        df = None
        try:
            df = self.dfStockInfoList['전업종지수']
            df.loc[jongmokName] = line 
        except KeyError:
            self.dfStockInfoList['전업종지수']= pd.DataFrame(columns = kw_util.dict_jusik['TR:전업종지수'])
            df = self.dfStockInfoList['전업종지수']
            df.loc[jongmokName] = line
        # print(df)
        pass
   
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
        # print(util.whoami() + 'sScrNo: {}, rQName: {}, trCode: {}, recordName: {}, prevNext: {}' 
        # .format(scrNo, rQName, trCode, recordName, prevNext))

        # rQName 은 개별 종목 코드임

        #주식 기본 정보 요청 
        if( trCode == "opt10001"):
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
            if( rQName in self.conditionOccurList):
                self.conditionOccurList.remove(rQName)
                QTimer.singleShot(200, self.sigGetTrCplt)
            pass
        # 업종 지수 요청 ex) 코스피 코스닥 
        elif( trCode == "opt20003"):
            self.makeOpt20003Info(rQName)
            pass

    # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmokCode, realType, realData):
        # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
        #         .format(jongmokCode, realType, realData))
        if( realType == "주식호가잔량"):
            print(jongmokCode,end =' ')
          
            # TODO: 엉뚱한 종목코드의 주식 호가 잔량이 넘어 오는 경우가 있으므로 확인해야함 
            self.makeHogaJanRyangInfo(jongmokCode)                
            self.processStopLoss(jongmokCode)
            pass

    # 실시간 호가 잔량 정보를 토대로 stoploss 수행         
    def makeHogaJanRyangInfo(self, jongmokCode):
        #주식 호가 잔량 정보 요청 
        jongmokName = None 
        line = [] 
        df = None
        result = None 
        for list in kw_util.dict_jusik['실시간-주식호가잔량']:
            if( list == "종목명" ):
                jongmokName = self.getMasterCodeName(jongmokCode)
                line.append(jongmokName)
                continue
            result = self.getCommRealData(jongmokCode, kw_util.dict_name_fid[list] ) 
            line.append(result.strip())

        try:
            df = self.dfStockInfoList["실시간-주식호가잔량"]
            df.loc[jongmokName] = line
        except KeyError:
            self.dfStockInfoList["실시간-주식호가잔량"] = pd.DataFrame(columns = kw_util.dict_jusik["실시간-주식호가잔량"])
            df = self.dfStockInfoList["실시간-주식호가잔량"]
            df.loc[jongmokName] = line

        # print(line)
        pass 



    def processStopLoss(self, jongmokCode):
        df = None
        jongmokName = self.getMasterCodeName(jongmokCode)
        try: 
            df = self.dfStockInfoList["잔고정보"]
            df.loc[jongmokName]
        except KeyError:
            return

        jangosuryang = int( df.loc[jongmokName, "주문가능수량"] )
        stop_loss, stop_plus = 0,0

        # 주식 거래 시간 종료가 가까운 경우 모든 종목 매도 
        if( datetime.time(*AUTO_TRADING_END_TIME) <  self.currentTime.time() ):
            # 바로 매도 해야 하므로 큰 값을 넣도록 함 
            stop_loss = int(df.loc[jongmokName, "매입단가"] ) * 100
        else:
            # 손절가는 매수시 기준가로 책정되어 있음 
            stop_loss = int(df.loc[jongmokName, "손절가"])
        
        stop_plus = int(df.loc[jongmokName, "이익실현가"])

        # 호가 정보는 문자열로 기준가 대비 + , - 값이 붙어 나옴 
        df = self.dfStockInfoList["실시간-주식호가잔량"]
        maesuHoga1 =  abs(int(df.loc[jongmokName, '매수호가1']))
        maesuHogaAmount1 =  int(df.loc[jongmokName, '매수호가수량1'])
        maesuHoga2 =  abs(int(df.loc[jongmokName, '매수호가2']))
        maesuHogaAmount2 =  int(df.loc[jongmokName, '매수호가수량2'])
        #    print( util.whoami() +  maeuoga1 + " " + maesuHogaAmount1 + " " + maesuHoga2 + " " + maesuHogaAmount2 )
        totalAmount =  maesuHoga1 * maesuHogaAmount1 + maesuHoga2 * maesuHogaAmount2
        # print( util.whoami() + jongmokName + " " + str(sum))

        isSell = False
        printData = jongmokCode + ' ' + jongmokName + ' ' 
        if( stop_loss >= maesuHoga1 ) :
            printData += "(손절매도주문)"
            isSell = True
        if( stop_plus < maesuHoga1 ) :
            if( totalAmount >= TOTAL_BUY_AMOUNT):
                printData += "(익절매도문주문)" 
                isSell = True 
            else:
                printData += "(익절시도호가수량부족 손절시도만함)" 
                util.save_log(printData, '손절시도만!', 'log')

        printData += "잔고수량: " + str(jangosuryang) 
        if( isSell == True ):
            result = self.sendOrder("sell_"  + jongmokCode, kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
                                jongmokCode, jangosuryang, 0 , kw_util.dict_order["시장가"], "")
            util.save_log(printData, '손절', 'log')
            print("S " + str(result), sep= "")
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
            jongmokCode = self.getChejanData(9001)[1:]
            boyouSuryang = int(self.getChejanData(930))
            if( boyouSuryang == 0 ):
                self.removeBuyCodeList(jongmokCode)
            else:
                self.makeJangoInfo(jongmokCode, fidList)
            pass

        elif ( gubun == "0"):
            jumun_sangtae =  self.getChejanData(913)
            jongmokCode = self.getChejanData(9001)[1:]
            jumun_gubun = self.getChejanData(905)[1:]
            if( jumun_sangtae == "체결"):
                if( jumun_gubun == "매수"):
                    pass
                elif(jumun_gubun == "매도"):
                    pass
                self.makeChegyelInfo(jongmokCode, fidList)
                pass
            pass
    def makeChegyelInfo(self, jongmokCode, fidList):
        fids = fidList.split(";")
        lineData = []
        printData = "" 
        keyIndex = util.cur_time_msec() 

        for chegyelDfColumn in kw_util.dict_jusik["체결정보"]:
            nFid = None
            result = ""
            try:
                nFid = kw_util.dict_name_fid[chegyelDfColumn]
            except KeyError:
                continue
                
            if( str(nFid) in fids):
                if( chegyelDfColumn == '종목코드'):
                    result = self.getChejanData(nFid)[1:]
                else: 
                    result = self.getChejanData(nFid)
            lineData.append(result.strip())
            printData += chegyelDfColumn + ": " + result + ", " 
        
        try:
            df = self.dfStockInfoList["체결정보"]
            df.loc[keyIndex] = lineData
        except KeyError:
            self.dfStockInfoList["체결정보"] = pd.DataFrame(columns = kw_util.dict_jusik['체결정보'])
            df = self.dfStockInfoList['체결정보']
            df.loc[keyIndex] = lineData
        util.save_log(printData, "*체결정보", folder= "log")
        pass

    def makeJangoInfo(self, jongmokCode, fidList):
        jongmokName = self.getMasterCodeName(jongmokCode)
        fids = fidList.split(";")
        lineData = []
        printData = "" 

        for jangoDfColumn in kw_util.dict_jusik["잔고정보"]:
            nFid = None
            result = ""
            try:
                if( jangoDfColumn == "발생시간"): # 없는 필드 이므로 
                    result = util.cur_date_time()
                elif( jangoDfColumn == "손절가"): # 기준가를 통해 손절가 계산 
                    tempFid =  kw_util.dict_name_fid["기준가"]      
                    result =  str( math.ceil(float(self.getChejanData(tempFid)) ))
                elif( jangoDfColumn == "이익실현가"):
                    tempFid =  kw_util.dict_name_fid["매입단가"]      
                    result =  str( math.ceil(float(self.getChejanData(tempFid)) * (1 + STOP_PLUS_PERCENT/100) ))
                else:
                    nFid = kw_util.dict_name_fid[jangoDfColumn]
            except KeyError:
                continue
                
            if( str(nFid) in fids):
                result = self.getChejanData(nFid)
            lineData.append(result)
            printData += jangoDfColumn + ": " + result + ", " 
        
        try: 
            df = self.dfStockInfoList["잔고정보"]
            df.loc[jongmokName] = lineData
        except KeyError:
            self.dfStockInfoList["잔고정보"] = pd.DataFrame(columns = kw_util.dict_jusik['잔고정보'])
            df = self.dfStockInfoList['잔고정보']
            df.loc[jongmokName] = lineData
        boyouSuryang = int(self.getChejanData(930))
        if( boyouSuryang !=  0):
            util.save_log(printData, "잔고정보", folder= "log")
        pass

    def insertBuyCodeList(self, jongmokCode):
        if( jongmokCode not in self.buyCodeList ):
            self.buyCodeList.append(jongmokCode)
            self.insertJanRyangCodeList(jongmokCode)
        pass

    #주식 호가 잔량 정보 요청리스트 삭제 
    def removeBuyCodeList(self, jongmokCode):
        if( jongmokCode in self.buyCodeList ):
            self.buyCodeList.remove(jongmokCode)
        self.removeJanRyangCodeList(jongmokCode)
        # 잔고 df frame 삭제 
        df = None
        try: 
            df = self.dfStockInfoList["잔고정보"]
        except KeyError:
            return
        jongmokName = self.getMasterCodeName(jongmokCode)
        self.dfStockInfoList["잔고정보"] = df.drop(jongmokName.strip())
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
            self.conditionOccurList.append({'종목코드': code}) 
            self.sigConditionOccur.emit()
        pass 

    def makeConditionOccurInfo(self, jongmokCode):
        line = []
        #발생시간, 종목코드,  종목명
        line.append(util.cur_date_time().strip() )
        line.append(jongmokCode)
        line.append(self.getMasterCodeName(jongmokCode))
        try:
            df = self.dfStockInfoList["조건진입"]
            df.loc[df.shape[0]] = line 
        except KeyError:
            self.dfStockInfoList["조건진입"] = pd.DataFrame(columns = kw_util.dict_jusik['조건진입'])
            df = self.dfStockInfoList['조건진입']
            df.loc[df.shape[0]] = line
        pass

    #주식 호가 잔량 정보 요청리스트 추가 
    def insertJanRyangCodeList(self, jongmokCode):
        codeList = []
        for code in self.buyCodeList:
            codeList.append(code)
        if( jongmokCode not in self.buyCodeList ):
            codeList.append(jongmokCode)
        # 실시간 호가 정보 요청 "0" 은 이전거 제외 하고 새로 요청
        self.setRealReg(kw_util.sendRealRegScreenNo, ';'.join(codeList), kw_util.dict_type_fids['주식호가잔량'], "0")

    #주식 호가 잔량 정보 요청리스트 삭제 
    def removeJanRyangCodeList(self, jongmokCode):
        # 버그로 모두 지우고 새로 등록하게 함 
        self.setRealRemove("ALL", "ALL")
        codeList  = []
        for code in self.buyCodeList:
            codeList.append(code)
        # 실시간 호가 정보 요청 "0" 은 이전거 제외 하고 새로 요청
        if( len(codeList) ):
           tmp = self.setRealReg(kw_util.sendRealRegScreenNo, ';'.join(codeList), kw_util.dict_type_fids['주식호가잔량'], "0")
           print(util.whoami() + ' return  ' + tmp)

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
        self.ocx.dynamicCall(
            "SendCondition(QString,QString, int, int)", scrNo, conditionName, index, search)

    # 실시간 조건검색을 중지합니다.
    # ※ 화면당 실시간 조건검색은 최대 10개로 제한되어 있어서 더 이상 실시간 조건검색을 원하지 않는 조건은 중지해야만 카운트 되지 않습니다.
    @pyqtSlot(str, str, int)
    def sendConditionStop(self, scrNo, conditionName, index):
        self.ocx.dynamicCall(
            "SendConditionStop(QString, QString, int)", scrNo, conditionName, index)

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
    # 예로 OPT10080을 살펴보면 OUTPUT의 멀티데이터의 항목처럼 현재가, 거래량, 체결시간등 순으로 항목의 위치가 0부터 1씩
    # 증가합니다.
    @pyqtSlot(str, str, result=str)
    def getCommDataEx(self, trCode, recordName):
        return self.ocx.dynamicCall("GetCommDataEx(QString, QString)", trCode, recordName)

    # 리얼 시세를 끊는다.
    # s화면 내 모든 리얼데이터 요청을 제거한다.
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

    def test_add_jongmok_save():
        objKiwoom.makeConditionOccurInfo('068330') 
        objKiwoom.makeConditionOccurInfo('021080') 
        objKiwoom.makeConditionOccurInfo('036620') 
        objKiwoom.makeConditionOccurInfo('127710') 
        objKiwoom.makeConditionOccurInfo('127710') 
        objKiwoom.makeConditionOccurInfo('033340') 
        objKiwoom.makeConditionOccurInfo('102280') 
        objKiwoom.makeConditionOccurInfo('065060') 
        objKiwoom.makeConditionOccurInfo('006910') 
        objKiwoom.makeConditionOccurInfo('005110') 
        objKiwoom.makeConditionOccurInfo('091590') 
        objKiwoom.makeConditionOccurInfo('093380') 
        objKiwoom.makeConditionOccurInfo('065240') 
        objKiwoom.makeConditionOccurInfo('064260') 
        objKiwoom.makeConditionOccurInfo('020560') 
        objKiwoom.makeConditionOccurInfo('014910') 
        objKiwoom.makeConditionOccurInfo('033340') 
        objKiwoom.makeConditionOccurInfo('115610') 
        objKiwoom.makeConditionOccurInfo('040350') 
        objKiwoom.makeConditionOccurInfo('049480') 
        objKiwoom.makeConditionOccurInfo('102280') 
        objKiwoom.makeConditionOccurInfo('065060') 
        objKiwoom.makeConditionOccurInfo('006910') 
        objKiwoom.makeConditionOccurInfo('005110') 
        objKiwoom.makeConditionOccurInfo('091590') 
        objKiwoom.makeConditionOccurInfo('035720') 
        objKiwoom.sigRequest1minTr.emit()
    def test_buy():
        # 정상 매수 - 우리종금 1주 
        # objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매수"], 
        # "010050", 1, 0 , kw_util.dict_order["시장가"], "")

        # 비정상 매수 (시장가에 단가 넣기 ) 우리종금 1주  
        # objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매수"], 
        # "010050", 1, 900 , kw_util.dict_order["시장가"], "")

        # 정상 매도 - 우리 종금 1주 
        # objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
        # "010050", 1, 0 , kw_util.dict_order["시장가"], "")
        
        # 정상 매수 - kd 건설 1주 
        objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매수"], 
        "044180", 1, 0 , kw_util.dict_order["시장가"], "")

        #정상 매도 - kd 건설 1주 
        # objKiwoom.sendOrder("buy", kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
        # "044180", 1, 0 , kw_util.dict_order["시장가"], "")
        # Execute the Application and Exit
        pass
    def test_save():
        objKiwoom.saveStockInfo()
        pass
    def test_condition():
        objKiwoom._OnReceiveRealCondition("044180", "I",  "단타 추세", 1)
        pass
    def test_yupjong():
        objKiwoom.requestOpt20003("1")
        objKiwoom.requestOpt20003("101")
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
    sys.exit(myApp.exec_())


