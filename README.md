## *사용상 부주의로 인한 책임은 사용자에게 있습니다*
# kw_condition
 - 키움 오픈 API + PyQt5 를 사용하여 console 형식으로 주식 매매를 자동으로 수행하는 프로그램
 - 키움증권의 조건 검색 기능을 이용하여 조건 검색에 해당하는 종목리스트를 얻어와 매매 수행
 - 추가 매수 기능 추가(추가 매수 수량 조절가능,  익절/손절 퍼센티지 조절 가능)
 - Google Spread 로 거래 내역 저장 기능 추가
 - slack 매수/매도 알림 추가  
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
1. HTS 상에서 조건식 생성 
1. user_setting.py 파일내에서 CONDITION_INFO 값을수정여 조건식 이름과 시작시간 설정 
1. 조건식에 만족하는 리스트의 매수할지 안할지 선택은? 
    - determineBuyProcessStateEntered 함수 참고
        - 위 함수는 이미 매입 종목 + 조건식 만족하는 종목 수 만큼 루프를 돌며 한종목당 주기는 20msec 임  
1. 매입 종목의 매도할지 안할지 선택은?
    - processStopLoss 함수 참고
        - 위 함수는 실시간 체결정보를 받을 때마다 매번 실행 됨 

----
## user_setting.py 내의  변수 설정 내용 

### 기본 설정
1. MAESU_UNIT = 100000 # 추가 매수 기본 단위 
1. BUNHAL_MAESU_LIMIT = 5 # 분할 매수 횟수 제한 
1. MAX_STOCK_POSSESION_COUNT = 3 # 제외 종목 리스트 불포함한 최대 종목 보유 수
1. BASIC_STOP_LOSS_PERCENT = -0.6 # 종목 전체 적용되는 stoploss
1. EXCEPTION_LIST = [''] # 장기 보유 종목 번호 리스트  ex) EXCEPTION_LIST = ['034220'] 


### [slack bot 만들기](https://yganalyst.github.io/web/slackbot1/)
1. SLACK_BOT_ENABLED = True  # slack 알림사용할지 여부 
1. SLACK_BOT_TOKEN = ""  # slack bot 접근 token 
1. SLACK_BOT_CHANNEL = ""  # slack channel 

### Google Spread 
GOOGLE_SPREAD_AUTH_JSON_FILE = 'test.json'  # 접근을위 권한파일  
GOOGLE_SPREAD_SHEET_NAME = '2월14일'   # 시트 이름

----
## StateMachine 정의 
![alt tag](https://user-images.githubusercontent.com/15916783/67251929-d2849500-f4ab-11e9-8c82-f2b5deaeb48e.png)

