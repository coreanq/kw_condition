# -*-coding: utf-8 -*-
import sys
import os
import re
import datetime
import time

import pandasmodel
from main_util import whoami, whosdaddy, cur_date_time
from kw_util import dict_fid_set, dict_jusik, parseErrorCode, sendConditionScreenNo, selectConditionName, sendRealRegScreenNo
import pandas as pd

from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl
from PyQt5.QtCore import QStateMachine, QState, QTimer, QFinalState
from PyQt5.QtWidgets import QApplication
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QAxContainer import QAxWidget

class KiwoomConditon(QObject):
    sigInitOk = pyqtSignal()
    sigConnected = pyqtSignal()
    sigDisconnected = pyqtSignal()
    sigGetConditionCplt = pyqtSignal()
    sigSelectCondition = pyqtSignal()
    sigRefreshCondition = pyqtSignal()
    sigCheckTrList = pyqtSignal()
    sigRequestTr = pyqtSignal()
    sigGetTrCplt = pyqtSignal()
    sigStateStop = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.fsm = QStateMachine()
        self.qmlEngine = QQmlApplicationEngine()
        self.account_list = []
        self.timerPolling = QTimer()
        # 감시 리스트는 감시할 모든 종목을 가지고 있고 
        # request 는 1초당 5번의 조회 제약으로 실제 tr 요청할 5개의 종목만을 가지고 있음 
        self.gamsiList = []
        self.requestList = []
        self.modelCondition = pandasmodel.PandasModel(pd.DataFrame(columns = ('조건번호', '조건명')))
        # 종목번호를 key 로 하여 pandas dataframe 을 value 로 함 
        self.dfList = {}
        self.create_states()
        self.createConnection()

    def create_states(self):
        # state defintion
        mainState = QState(self.fsm)       
        finalState = QFinalState(self.fsm)
        self.fsm.setInitialState(mainState)
        
        initState = QState(mainState)
        disconnectedState = QState(mainState)
        connectedState = QState(QtCore.QState.ParallelStates, mainState)
        
        conditionState = QState(connectedState)
        trState = QState(connectedState)
        
        initConditionState = QState(conditionState)
        waitSelectingConditionState = QState(conditionState)
        processingConditionState = QState(conditionState)
        
        initTrState = QState(trState)
        trRequestingState = QState(trState)
        
        
        #transition defition
        mainState.setInitialState(initState)
        mainState.addTransition(self.sigStateStop, finalState)
        initState.addTransition(self.sigInitOk, disconnectedState)
        disconnectedState.addTransition(self.sigConnected, connectedState)
        disconnectedState.addTransition(self.sigDisconnected, disconnectedState)
        connectedState.addTransition(self.sigDisconnected, disconnectedState)
        
        conditionState.setInitialState(initConditionState)
        initConditionState.addTransition(self.sigGetConditionCplt, waitSelectingConditionState)
        waitSelectingConditionState.addTransition(self.sigSelectCondition, processingConditionState)
        processingConditionState.addTransition(self.sigRefreshCondition, initConditionState)
        
        trState.setInitialState(initTrState)
        initTrState.addTransition(self.sigCheckTrList, initTrState)
        initTrState.addTransition(self.sigRequestTr, trRequestingState)
        trRequestingState.addTransition(self.sigGetTrCplt, initTrState)
        
        #state entered slot connect
        mainState.entered.connect(self.mainStateEntered)
        initState.entered.connect(self.initStateEntered)
        disconnectedState.entered.connect(self.disconnectedStateEntered)
        connectedState.entered.connect(self.connectedStateEntered)
        
        conditionState.entered.connect(self.conditionStateEntered)
        trState.entered.connect(self.trStateEntered)
        
        initConditionState.entered.connect(self.initConditionStateEntered)
        waitSelectingConditionState.entered.connect(self.waitSelectingConditionStateEntered)
        processingConditionState.entered.connect(self.processingConditionStateEntered)
        
        initTrState.entered.connect(self.initTrStateEntered)
        trRequestingState.entered.connect(self.trRequestingStateEntered)
        
        finalState.entered.connect(self.finalStateEntered)
        
        #fsm start
        self.fsm.start()
        
    @pyqtSlot()
    def mainStateEntered(self):
        print(whoami())
        pass

    @pyqtSlot()
    def initStateEntered(self):
        print(whoami())
        self.sigInitOk.emit()
        pass

    @pyqtSlot()
    def disconnectedStateEntered(self):
        print(whoami())
        self.commConnect()
        pass

    @pyqtSlot()
    def connectedStateEntered(self):
        print(whoami())
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

        print(whoami() + 'account list ' + str(self.account_list))
        pass

    @pyqtSlot()
    def conditionStateEntered(self):
        pass

    @pyqtSlot()
    def trStateEntered(self):
        pass

    @pyqtSlot()
    def initConditionStateEntered(self):
        print(whoami() )
        # get 조건 검색 리스트
        self.getConditionLoad()
        pass

    @pyqtSlot()
    def waitSelectingConditionStateEntered(self):
        print(whoami() )
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
        # print(whoami() + str(self.dictCondition) +' ' + name)
        conditionNum = 0 
        for number, condition in tempDict.items():
            if condition == selectConditionName:
                    conditionNum = int(number)
        print(sendConditionScreenNo, selectConditionName, conditionNum)
        self.sendCondition(sendConditionScreenNo, selectConditionName, conditionNum,  1)
        
        self.sigSelectCondition.emit()

        pass

    @pyqtSlot()
    def processingConditionStateEntered(self):
        print(whoami())
        # self.sigRefreshCondition.emit()
        pass

    @pyqtSlot()
    def initTrStateEntered(self):
        print(".", end='')
        for index, jongmokCode in enumerate(self.gamsiList):
            if( index >= 5 ):
                break
            self.requestList.append(jongmokCode)
        
        for jongmokCode in self.requestList:
            self.gamsiList.remove(jongmokCode)

       
        if( len(self.requestList)):
            self.sigRequestTr.emit()
             # 기존 gamsiList update 를 위해서 requestList 만큼 떼어내서 뒤로 다시 붙임 
             # 리스트를 가져다 붙일때는 extend 사용
            self.gamsiList.extend(self.requestList)
        else:
            QTimer.singleShot(1000, self.sigCheckTrList)
        pass

    @pyqtSlot()
    def trRequestingStateEntered(self):
        print(cur_date_time() + whoami())
        for code in self.requestList:
            self.setInputValue("종목코드",code ) 
            self.setInputValue("틱범위","1:1분") 
            self.setInputValue("수정주가구분","0") 
            print( whoami() + parseErrorCode( self.commRqData(code , "opt10080", 0, '0001')) )
        pass

    @pyqtSlot()
    def finalStateEntered(self):
        print(whoami())
        pass

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

        self.timerPolling.setInterval(10000)
        self.timerPolling.timeout.connect(self.onPollingTimeout)

    def insertGamsiList(self, jongmokCode):
        if( jongmokCode in self.gamsiList):
            print(whoami() + "jongmok Code already exists")
            pass
        else:
            self.gamsiList.append(jongmokCode)
            self.sigCheckTrList.emit()
            pass

    @pyqtSlot()
    def onPollingTimeout(self):
        pass

    @pyqtSlot()
    def quit(self):
        print(whoami())
        self.commTerminate()
        QApplication.quit()

    # 에러코드의 메시지를 출력한다.
    @pyqtSlot(int, result=str)
    def parseErrorCode(self, errCode):
        return util.parseErrorCode(errCode)

    # event
    # 통신 연결 상태 변경시 이벤트
    # nErrCode가 0이면 로그인 성공, 음수면 실패
    def _OnEventConnect(self, errCode):
        print(whoami() + '{}'.format(errCode))
        if errCode == 0:
            self.sigConnected.emit()
        else:
            self.sigDisconnected.emit()

    # 수신 메시지 이벤트
    def _OnReceiveMsg(self, scrNo, rQName, trCode, msg):
        print(whoami() + 'sScrNo: {}, sRQName: {}, sTrCode: {}, sMsg: {}'
        .format(scrNo, rQName, trCode, msg))
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
        pass
    # Tran 수신시 이벤트
    def _OnReceiveTrData(   self, scrNo, rQName, trCode, recordName,
                            prevNext, dataLength, errorCode, message,
                            splmMsg):
        print(whoami() + 'sScrNo: {}, rQName: {}, trCode: {}, recordName: {}, prevNext: {}' 
        .format(scrNo, rQName, trCode, recordName,prevNext))

        repeatCnt = self.getRepeatCnt(trCode, rQName)
        for i in range(repeatCnt):
            line = []
            for list in dict_jusik['분봉TR']:
                if( list == "종목명" ):
                    line.append(self.getMasterCodeName(rQName))
                    continue
                result = self.getCommData(trCode, rQName, i, list)
                line.append(result)

            # print(line)
            timeIndex = dict_jusik['분봉TR'].index("체결시간")
            currentTimeStr =line[timeIndex]

            # 오늘 이전 데이터는 받지 않는다
            resultTime = time.strptime(currentTimeStr.strip(),  "%Y%m%d%H%M%S")
            currentTime = time.localtime()
            if( resultTime.tm_mday == currentTime.tm_mday ):
                # 기존에 저장되어 있는 않는 데이터만 저장하고 이미 데이터가 있는 경우 리턴한다. 
                try:
                    df = self.dfList[rQName]
                    # any 를 해야 dataframe 이 리턴되지 않고 True, False 로 리턴됨 
                    if((df['체결시간'] == currentTimeStr).any() ):
                        #중복 나올시 바로 나옴 
                        break
                    else:
                        # print(line)
                        df.loc[df.shape[0]] = line 
                except KeyError:
                    self.dfList[rQName] = pd.DataFrame(columns = dict_jusik['분봉TR'])
                    df = self.dfList[rQName]
                    df.loc[df.shape[0]] = line
                    print(line)
            else:
                break

        if( rQName in self.requestList):
            self.requestList.remove(rQName)
        if( len(self.requestList) == 0 ):
            self.sigGetTrCplt.emit()

               # 실시간 시세 이벤트
    def _OnReceiveRealData(self, jongmokCode, realType, realData):
        # print(whoami() + 'jongmokCode: {}, realType: {}, realData: {}'
        #         .format(jongmokCode, realType, realData))
        '''
        real Data Sample
               "주식체결" : ("체결시간", 
                            "현재가",
	                        "전일대비",
	                        "등락율",
	                        "(최우선)매도호가",
	                        "(최우선)매수호가",
                            "거래량",
	                        "누적거래량",
	                        "누적거래대금",
	                        "시가",
	                        "고가",
	                        "저가",
    	                    "전일대비기호",
	                        "전일거래량대비(계약,주)",
	                        "거래대금증감",
	                        "전일거래량대비(비율)",
	                        "거래회전율",
	                        "거래비용",
	                        "체결강도",
	                        "시가총액(억)",
	                        "장구분",
	                        "KO접근도",
	                        "상한가발생시간",
	                        "하한가발생시간")
                            
        100952	 1533000	 0	      0.00	+1534000	 1533000	-1	44078	67432	-1528000	+1537000	-1522000	3	-187266	-284986212331	-19.05	0.03	5075	97.56	2191720	2	0	000000	000000
        '''
        # if realType == '주식체결':
        #     jongmokName = self.getMasterCodeName(jongmokCode)
        #     # shape 의 경우 2차원 배열의 사이즈를 나타냄 
        #     # 맨 마지막 행의 시간을 비교해 1분이 넘었으면 데이터를 추가하도록 함 
        #     lastIndex = self.dfCurrent.shape[0]
        #     if( lastIndex ) :
        #         lastRow = self.dfCurrent.loc[lastIndex - 1 ]
        #         previousTradeTime = lastRow.loc['체결시간']
        #         currentTradeTime = realData.split()[0]
        #         preTime = datetime.time(int(previousTradeTime[:2]), int(previousTradeTime[2:4], 0))
        #         curTime = datetime.time(int(currentTradeTime[:2]), int(currentTradeTime[2:4], 0))
        #         if( preTime < curTime ):  
        #             self.dfCurrent.loc[self.dfCurrent.shape[0]] = (jongmokCode, jongmokName) + tuple(realData.split()) 
        #             #최근 10개의 자료를 컬럼을 선택하여 뿌려줌 이때 ix 사용함 (mixed index) 
        #             print(self.dfCurrent.ix[-5:, ("종목코드", "종목이름", "체결시간", "현재가", "전일대비", "등락율", "거래량", "누적거래량","시가", "고가", "저가")]) 
        #     else:
        #         self.dfCurrent.loc[self.dfCurrent.shape[0]] = (jongmokCode, jongmokName) + tuple(realData.split()) 
            

    # 체결데이터를 받은 시점을 알려준다.
    # sGubun – 0:주문체결통보, 1:잔고통보, 3:특이신호
    # sFidList – 데이터 구분은 ‘;’ 이다.
    def _OnReceiveChejanData(self, gubun, itemCnt, fidList):
        print(whoami() + 'gubun: {}, itemCnt: {}, fidList: {}'
                .format(gubun, itemCnt, fidList))

    # 로컬에 사용자조건식 저장 성공여부 응답 이벤트
    # 0:(실패) 1:(성공)
    def _OnReceiveConditionVer(self, ret, msg):
        print(whoami() + 'ret: {}, msg: {}'
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
        print(whoami() + 'scrNo: {}, codeList: {}, conditionName: {} '
        'index: {}, next: {}'
        .format(scrNo, codeList, conditionName, index, next ))
         
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
        print(whoami() + 'code: {}, type: {}, conditionName: {}, conditionIndex: {}'
        .format(code, type, conditionName, conditionIndex ))
        typeName = ''
    
        if type == 'I':
            typeName = '진입'
            self.insertGamsiList(code)
        else:
            typeName = '이탈'
        print('{}: name: {}, status: {}'
        .format(cur_date_time(), self.getMasterCodeName(code), typeName))
         # self.setInputValue("종목코드","034940") 
        # self.setInputValue("틱범위","1:1분") 
        # self.setInputValue("수정주가구분","0") 
        # print( whoami() + parseErrorCode( self.commRqData("034940", "opt10080", 0, '0001')) )


    # method 
    # 로그인
    # 0 - 성공, 음수값은 실패
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
    @pyqtSlot(str, str, str, int, result=int)
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
        return json.dumps(self.ocx.dynamicCall("GetCommDataEx(QString, QString)", trCode, recordName))

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
    # Execute the Application and Exit
    sys.exit(myApp.exec_())

