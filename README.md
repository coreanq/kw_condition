## *사용상 부주의로 인한 책임은 사용자에게 있습니다*
# kw_condition
 - 키움 오픈 API + PyQt5 를 사용하여 console 형식으로 주식 매매를 자동으로 수행하는 프로그램
 - 키움증권의 조건 검색 기능을 이용하여 조건 검색에 해당하는 종목리스트를 얻어와 매매 수행
 - 추가 매수 기능 추가(추가 매수 수량 조절가능,  익절/손절 퍼센티지 조절 가능)
 - 엑셀로 거래 내역 저장 기능 추가 
 - 
 - <a href="https://www.youtube.com/watch?v=QnnO4kIj51c" target="_blank"><img src="http://img.youtube.com/vi/YOUTUBE_VIDEO_ID_HERE/0.jpg" 
alt="키움증권 조건검색 사용 가이드" width="300" height="" border="10" /></a>

## 개발 환경  
 - Windows 64bit 권장
 - [키움증권 Open API+](https://www1.kiwoom.com/nkw.templateFrameSet.do?m=m1408000000)
 - [Python Anaconda 4.2.0 (python 3.7) 32bit](https://www.continuum.io/downloads#windows) 32bit 버전 필수 
 - [PyQt 5.9.2 32bit] in Python Anaconda 32bit 버전 필수 
 - [키움 오픈 API](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.5.pdf)

## 참고 소스 
 - from https://github.com/sculove/QWebview-plus

## 실행방법 
~~~~
 > python main.py 
~~~~

## 사용방법
1. 사용자가 설정한 조건식을 시간마다 활성화 시키기 위해서는 
    - onTimerSystemTimeout 함수 참고
1. 조건식에 만족하는 리스트의 매수할지 안할지 선택은? 
    - determineBuyProcessStateEntered 함수 참고
        - 위 함수는 매입 종목 + 조건식 만족하는 종목 수 만큼 루프를 돌며 한종목당 주기는 20msec 임  
1. 매입 종목의 매도할지 안할지 선택은?
    - processStopLoss 함수 참고
        - 위 함수는 실시간 체결정보를 받을 때마다 매번 실행 됨 


> main.py 내의  변수 설정 내용 

> AUTO_TRADING_OPERATION_TIME = [ [ [8, 50], [15, 19] ] ]  # 8시 50분에 동작해서 15시 19분에 자동 매수/매도 정지/  매도호가 정보의 경우 동시호가 시간에도  올라오므로 주의

> MAESU_UNIT = 100000 # 추가 매수 기본 단위 

> BUNHAL_MAESU_LIMIT = 5 # 분할 매수 횟수 제한 

> MAX_STOCK_POSSESION_COUNT = 3 # 제외 종목 리스트 불포함한 최대 종목 보유 수

> BASIC_STOP_LOSS_PERCENT = -0.6 # 종목 전체 적용되는 stoploss

> EXCEPTION_LIST = [''] # 장기 보유 종목 번호 리스트  ex) EXCEPTION_LIST = ['034220'] 

## StateMachine 정의 
![alt tag](https://user-images.githubusercontent.com/15916783/67251929-d2849500-f4ab-11e9-8c82-f2b5deaeb48e.png)

