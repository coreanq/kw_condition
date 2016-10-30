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


# STOCK_TRADE_TIME = [ [ [9, 10], [10, 00] ], [ [14, 20], [15, 10] ] ]
STOCK_TRADE_TIME = [ [ [9, 5], [15, 10] ]]
TIME_CUT_MIN = 20  
STOP_PLUS_PERCENT = 3.5
STOP_LOSS_PERCENT = 2.5 
TOTAL_BUY_AMOUNT = 50000000 # 5000만 이상 안되면 구매 안함 (슬리피지 최소화) 
STOCK_PRICE_MIN_MAX = { 'min': 2000, 'max':50000} #조건 검색식에서 오류가 가끔 발생하므로 검증 루틴 넣음 

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
        
        conditionState = QState(connectedState)
        purchaseState = QState(connectedState)
        
        initConditionState = QState(conditionState)
        waitingSelectConditionState = QState(conditionState)
        standbyConditionState = QState(conditionState)
        prepare1minTrListState = QState(conditionState)
        request1minTrState = QState(conditionState)

        initPurchaseState = QState(purchaseState)
        
        
        #transition defition
        mainState.setInitialState(initState)
        mainState.addTransition(self.sigStateStop, finalState)
        mainState.addTransition(self.sigStockComplete, stockCompleteState)
        stockCompleteState.addTransition(self.sigStateStop, finalState)
        initState.addTransition(self.sigInitOk, disconnectedState)
        disconnectedState.addTransition(self.sigConnected, connectedState)
        disconnectedState.addTransition(self.sigTryConnect,  disconnectedState)
        connectedState.addTransition(self.sigDisconnected, disconnectedState)
        
        conditionState.setInitialState(initConditionState)
        initConditionState.addTransition(self.sigGetConditionCplt, waitingSelectConditionState)
        waitingSelectConditionState.addTransition(self.sigSelectCondition, standbyConditionState)
        standbyConditionState.addTransition(self.sigRefreshCondition, initConditionState)
        standbyConditionState.addTransition(self.sigRequest1minTr,prepare1minTrListState ) 
        prepare1minTrListState.addTransition(self.sigPrepare1minTrListComplete, request1minTrState) 
        request1minTrState.addTransition(self.sigGetTrCplt, request1minTrState) 
        
        purchaseState.setInitialState(initPurchaseState)

        #state entered slot connect
        mainState.entered.connect(self.mainStateEntered)
        stockCompleteState.entered.connect(self.stockCompleteStateEntered)
        initState.entered.connect(self.initStateEntered)
        disconnectedState.entered.connect(self.disconnectedStateEntered)
        connectedState.entered.connect(self.connectedStateEntered)
        
        conditionState.entered.connect(self.conditionStateEntered)
        purchaseState.entered.connect(self.trStateEntered)
        
        initConditionState.entered.connect(self.initConditionStateEntered)
        waitingSelectConditionState.entered.connect(self.waitingSelectConditionStateEntered)
        standbyConditionState.entered.connect(self.standbyConditionStateEntered)
        prepare1minTrListState.entered.connect(self.prepare1minTrListStateEntered)
        request1minTrState.entered.connect(self.request1minTrStateEntered) 

        initPurchaseState.entered.connect(self.initPurchaseStateEntered)
        
        finalState.entered.connect(self.finalStateEntered)
        
        #fsm start
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
        result = False
        for start, stop in STOCK_TRADE_TIME:
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
                result = True
        # 가능한 시간이 아니라면 바로 리턴     
        if( result == False ):
            return False
        # 종목 코드를 확인해 현재 업종 지수가 + 인경우만 거래 가능하도록 함  
        # 종합(KOSDAQ) or 종합(KOSPI)
        df = None
        yupjong = ""
        # yupjong 는 df 내의 종목명으로 넣어서 검색 가능하게 함 
        if( jongmokCode in self.kospiCodeList):
            yupjong = "종합(KOSPI)"
        elif( jongmokCode in self.kosdaqCodeList):
            yupjong = "종합(KOSDAQ)"
        
        if( yupjong == "" ):
            return False

        try:
            df = self.dfStockInfoList['전업종지수']
            updownPercent = df.loc[yupjong, '등락률']
            # print(yupjong, updownPercent)
            if( '+' in updownPercent):
                result = True
            else:
                result = False
        except KeyError:
            result = False 

        return result 
        pass
  
    @pyqtSlot()
    def mainStateEntered(self):
        self.loadStockInfoExcel()
        self.timerSystem.start()
        print(util.whoami())
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
        print(util.whoami())
        self.sigInitOk.emit()
        pass

    @pyqtSlot()
    def disconnectedStateEntered(self):
        print(util.whoami())
        if( self.getConnectState() == 0 ):
            self.commConnect()
            QTimer.singleShot(90000, self.sigTryConnect)
            pass
        else:
            self.sigConnected.emit()
            
    @pyqtSlot()
    def connectedStateEntered(self):
        print(util.whoami())
        # ui 현시
        self.initQmlEngine()
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
    def conditionStateEntered(self):
        pass

    @pyqtSlot()
    def initConditionStateEntered(self):
        print(util.whoami() )
        # get 조건 검색 리스트
        self.getConditionLoad()
        pass

    @pyqtSlot()
    def waitingSelectConditionStateEntered(self):
        print(util.whoami() )
        # 반환값 : 조건인덱스1^조건명1;조건인덱스2^조건명2;…;
        # result = '조건인덱스1^조건명1;조건인덱스2^조건명2;'
        result = self.getConditionNameList()
        searchPattern = r'(?P<index>[^\/:*?"<>|;]+)\^(?P<name>[^\/:*?"<>|;]+);'
        fileSearchObj = re.compile(searchPattern, re.IGNORECASE)
        findList = fileSearchObj.findall(result)
        
        
        tempDict = dict(findList)
        print(tempDict)
        
        # for condition_num, condition_name in tempDict.items():
        #     df = self.modelCondition._data
        #     df.loc[len(self.modelCondition)] = (condition_num, condition_name)
        #     self.modelCondition.refresh()
             
        # print(self.modelCondition)
        
        # name = self.dictCondition['001']
        # print(util.whoami() + str(self.dictCondition) +' ' + name)
        conditionNum = 0 
        for number, condition in tempDict.items():
            if condition == kw_util.selectConditionName:
                    conditionNum = int(number)
        print("select condition" + kw_util.sendConditionScreenNo, kw_util.selectConditionName, conditionNum)
        self.sendCondition(kw_util.sendConditionScreenNo, kw_util.selectConditionName, conditionNum,  1)
        
        self.sigSelectCondition.emit()

        pass

    @pyqtSlot()
    def standbyConditionStateEntered(self):
        print(util.whoami() )
        jangoList = [] 
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

    # 주식 기본정보 요청 
    def requestOpt10001(self, jongmokCode):
        self.setInputValue("종목코드", jongmokCode) 
        ret = self.commRqData(jongmokCode, "opt10001", 0, kw_util.sendJusikGobonScreenNo) 
        
        errorString = None
        if( ret != 0 ):
            errorString =   jongmokCode + " commRqData() " + kw_util.parseErrorCode(str(ret))
            print(util.whoami() + errorString ) 
            util.save_log(errorString, util.whoami(), folder = "log" )
        pass

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

    @pyqtSlot()
    def initPurchaseStateEntered(self):
        pass
     
    @pyqtSlot()
    def trStateEntered(self):
        pass

    @pyqtSlot()
    def finalStateEntered(self):
        print(util.whoami())
        pass
   
    @pyqtSlot()
    def onTimerSystemTimeout(self):
        print(".", end='') 
        self.currentTime = datetime.datetime.now()

        if( self.getConnectState() != 1 ):
            util.save_log("Disconnected!", "시스템", folder = "log")
            self.sigDisconnected.emit() 
        else:
            if( self.currentTime.hour >= 15 and self.currentTime.minute  >= 40): 
                util.save_log("Stock Trade Terminate!", "시스템", folder = "log")
                self.sigRequest1minTr.emit()
                pass
            else :
                # 코스피 코스닥 업종 현재가 요청 
                self.requestOpt20003('001')
                self.requestOpt20003('101')
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
        # .format(scrNo, rQName, trCode, recordName,prevNext))

        if( trCode == "opt10080"):
            # rQName 은 개별 종목 코드임 
            self.makeOpt10080Info(rQName)
            if( rQName in self.conditionOccurList):
                self.conditionOccurList.remove(rQName)
                QTimer.singleShot(200, self.sigGetTrCplt)
            pass
        elif( trCode == "opt20003"):
            self.makeOpt20003Info(rQName)
            pass
        #주식 기본 정보 요청 완료 후 매수 여부 판단 
        elif( trCode == "opt10001"):
            self.makeOpt10001Info(rQName)
            pass

    #주식 기본 정보 
    def makeOpt10001Info(self, rQName):
        index = 0
        line = []
        jongmokName = ""
        for list in kw_util.dict_jusik['TR:주식기본정보']:
            result = self.getCommData("opt10001", rQName, index, list)
            if( list == '종목명'):
                jongmokName = result.strip()
            line.append(result.strip())
      # print(line)
        df = None
        try:
            df = self.dfStockInfoList['주식기본정보']
            df.loc[jongmokName] = line 
        except KeyError:
            self.dfStockInfoList['주식기본정보']= pd.DataFrame(columns = kw_util.dict_jusik['TR:주식기본정보'])
            df = self.dfStockInfoList['주식기본정보']
            df.loc[jongmokName] = line
        # print(df)
        pass
    
    # 전업종 지수
    def makeOpt20003Info(self, rQName):
        # repeatCnt = self.getRepeatCnt("opt20003", rQName)
        # kospi 와 kosdaq 만 얻을 것이므로 몇 첫번째 데이터만 취함 
        index = 0
        line = []
        jongmokName = ""
        for list in kw_util.dict_jusik['TR:전업종지수']:
            result = self.getCommData("opt20003", rQName, index, list)
            if( list == '종목명'):
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
        
    # 1분봉 데이터 생성 --> to dataframe
    def makeOpt10080Info(self, rQName):
        repeatCnt = self.getRepeatCnt("opt10080", rQName)
        currentTimeStr  = None 
        for i in range(repeatCnt):
            line = []
            for list in kw_util.dict_jusik['TR:분봉']:
                if( list == "종목명" ):
                    line.append(self.getMasterCodeName(rQName))
                    continue
                result = self.getCommData("opt10080", rQName, i, list)
                if( list == "체결시간"):
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

    # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmokCode, realType, realData):
        # print(util.whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
        #         .format(jongmokCode, realType, realData))
        if( realType == "주식호가잔량"):
            # 엉뚱한 종목코드의 주식 호가 잔량이 넘어 오는 경우가 있으므로 확인해야함 
            self.makeHogaJanRyangInfo(jongmokCode)
            jongmokName = self.getMasterCodeName(jongmokCode)
            # 잔량 정보 요청은 첫 조건 진입시 한번만 해야 하므로 리스트에서 지움                
            self.removeJanRyangCodeList(jongmokCode)
            self.processStopLoss(jongmokCode)
            self.processBuy(jongmokCode)
            pass
               
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
        isTimeCut = False
        try: 
            df = self.dfStockInfoList["잔고정보"]
            df.loc[jongmokName]
        except KeyError:
            return
        maesu_time_str = df.loc[jongmokName, "발생시간"]
        jangosuryang = int( df.loc[jongmokName, "주문가능수량"] )

        currentTime = datetime.datetime.strptime(util.cur_date_time(),  "%Y-%m-%d %H:%M:%S")
        maesu_time =  datetime.datetime.strptime(maesu_time_str, "%Y-%m-%d %H:%M:%S")

        time_span = (currentTime - maesu_time).total_seconds()
        # 타임컷을 넘은 경우 매입단가로 손절가를 높임 
        if( time_span > 60 * TIME_CUT_MIN ):
            isTimeCut = True
            # 타임컷을 넘고 매입단가 근처서 왔다갔다 하는것을 막기 위해 바로 매도
            stop_loss = int(df.loc[jongmokName, "매입단가"] ) * 100
        else:
            stop_loss = int(df.loc[jongmokName, "손절가"])
        
        df.loc[jongmokName, "손절가"] = stop_loss
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
        printData = ""
        if( stop_loss >= maesuHoga1 ) :
            if( isTimeCut == True ) :
                printData += "타임컷 손절매도주문: "
            else:
                printData += "손절매도주문: "
            isSell = True
        if( stop_plus < maesuHoga1 ) :
            if( totalAmount >= TOTAL_BUY_AMOUNT):
                printData += "익절매도문주문: " 
                isSell = True 
            else:
                printData += "익절시도수량부족: " 
                printData += jongmokCode + " " + jongmokName + " 잔고수량 " + str(jangosuryang) 
                util.save_log(printData, '손절시도만!', 'log')

        printData += jongmokCode + " " + jongmokName + " 잔고수량 " + str(jangosuryang) 
        if( isSell == True ):
            result = self.sendOrder("sell_"  + jongmokCode, kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매도"], 
                                jongmokCode, jangosuryang, 0 , kw_util.dict_order["시장가"], "")
            util.save_log(printData, '손절', 'log')
            print("S " + str(result), sep= "")
            pass
        pass


    def processBuy(self, jongmokCode):
        if( self.isTradeAvailable(jongmokCode) ):        
            # 기존 매수한 종목인 경우 매수 금지 
            if( len(self.buyCodeList) ):
                return
            # 호가 창을 보고 매수 할지 안할지 여부 결정
            dfHoga = None
            jongmokName = self.getMasterCodeName(jongmokCode)
        
            try:
                dfHoga = self.dfStockInfoList["실시간-주식호가잔량"]
                dfHoga.loc[jongmokName]
            except KeyError:
                return

            # 이미 구매한적이 있는 종목의 경우 매수 금지 
            try: 
                df = self.dfStockInfoList["체결정보"]
                if( len( df[ df['종목코드'].isin([jongmokCode]) == True ] ) ) :
                    return
            except KeyError:
                pass

            # 호가 정보는 문자열로 기준가 대비 + , - 값이 붙어 나옴 
            maedoHoga1 =  abs(int(dfHoga.loc[jongmokName, '매도호가1']))
            maedoHogaAmount1 =  int(dfHoga.loc[jongmokName, '매도호가수량1'])
            maedoHoga2 =  abs(int(dfHoga.loc[jongmokName, '매도호가2']))
            maedoHogaAmount2 =  int(dfHoga.loc[jongmokName, '매도호가수량2'])
            #    print( util.whoami() +  maedoHoga1 + " " + maedoHogaAmount1 + " " + maedoHoga2 + " " + maedoHogaAmount2 )
            totalAmount =  maedoHoga1 * maedoHogaAmount1 + maedoHoga2 * maedoHogaAmount2 
            # print( util.whoami() + jongmokName + " " + str(sum) + (" won") ) 
            util.save_log( '{0:^20} 호가1:{1:>8}, 잔량1:{2:>8} / 호가2:{3:>8}, 잔량2:{4:>8}'
                    .format(jongmokName, maedoHoga1, maedoHogaAmount1, maedoHoga2, maedoHogaAmount2), '호가잔량' , folder= "log") 

            if( totalAmount >= TOTAL_BUY_AMOUNT):
                if( maedoHoga1 >= STOCK_PRICE_MIN_MAX['min'] and maedoHoga1 <= STOCK_PRICE_MIN_MAX['max']):
                    util.save_log(jongmokName, "매수주문", folder= "log")
                    result = self.sendOrder("buy_" + jongmokCode, kw_util.sendOrderScreenNo, objKiwoom.account_list[0], kw_util.dict_order["신규매수"], 
                            jongmokCode, 1, 0 , kw_util.dict_order["시장가"], "")
                    print("B " + str(result) , sep="")
                    # BuyCode List 에 넣지 않으면 호가 정보가 빠르게 올라오는 경우 계속 매수됨   
                    self.insertBuyCodeList(jongmokCode)
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
                elif( jangoDfColumn == "손절가"): # 매입단가를 통해 계산 
                    tempFid =  kw_util.dict_name_fid["매입단가"]      
                    result =  str( math.ceil(float(self.getChejanData(tempFid)) * (1 - STOP_LOSS_PERCENT/100) ))
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
            self.makeConditionOccurInfo(code)
            if( self.isTradeAvailable(code) == False ) :
                util.save_log(printLog, "조건진입(거래불가능)", folder = "log" )
                return
            if( len(self.buyCodeList) == 0 ):
                self.insertJanRyangCodeList(code)
                util.save_log(printLog, "조건진입(미보유)", folder = "log")
                pass
            else:
                util.save_log(printLog, "조건진입(보유)", folder = "log")
            print("!")
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
        if( jongmokCode not in self.buyCodeList ):
            self.setRealRemove(kw_util.sendRealRegScreenNo, jongmokCode)
        # setRealReg의 경우 "0" 은 이전거 제외 하고 새로 요청,  리스트가 없는 경우는 아무것도 안함 
        # if( len(codeList ) ):
        #     self.setRealReg(kw_util.sendRealRegScreenNo, ';'.join(codeList), kw_util.dict_type_fids['주식호가잔량'], "0")
        # else :

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
    sys.exit(myApp.exec_())


