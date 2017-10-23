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
 - Windows 32bit 권장
 - [키움증권 Open API+](https://www1.kiwoom.com/nkw.templateFrameSet.do?m=m1408000000)
 - [Python Anaconda 4.2.0 (python 3.5) 32bit](https://www.continuum.io/downloads#windows)
 - [PyQt 5.9.2 32bit](https://www.riverbankcomputing.com/software/pyqt/download5)
 - [키움 오픈 API](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.1.pdf)

## 참고 소스 
 - from https://github.com/sculove/QWebview-plus

## 사용 예
~~~~
 > python main.py 
~~~~

> main.py 내의  변수 설정 내용 

>  AUTO_TRADING_OPERATION_TIME = [ [ [9, 5], [15, 10] ]] # 해당 시스템 동작 시간 설정 -->  9시 5분 부터 15시 10분까지만 동작
> CONDITION_NAME = '급등' #키움증권 HTS 에서 설정한 조건 검색 식 이름

> TOTAL_BUY_AMOUNT = 50000000 #  매도 호가1, 매도 호가 2의 총 수량이 5000만원 이상 안되면 매수금지  (슬리피지 최소화)

> MAESU_BASE_UNIT  = 각 추가 매수 단계 마다 적용되는 기본 단위 

> MAESU_LIMIT = 3  # 추가 매수 3번 제한

> MAESU_TOTAL_PRICE  # 각 추가 매수시 매수 금액 설정 

> STOP_PLUS_PER_MAESU_COUNT # 각 추가 매수 단계마다 익절 퍼센티지 설정 

> STOP_LOSS_PER_MAESU_COUNT # 각 추가 매수 단계마다 손절 퍼센티지 설정 

> EXCEPTION_LIST = [] # 장기 보유 종목 번호 리스트  ex) EXCEPTION_LIST = ['034220'] 

> STOCK_POSSESION_COUNT  # 총 전체 주식 보유 갯수( 이 값보다 이상으로는 매수 안됨)

## StateMachine 정의 
![alt tag](https://user-images.githubusercontent.com/15916783/31872844-28055208-b7fa-11e7-9ea9-e71b66b00650.png)

## License
Licensed under MIT:

https://opensource.org/licenses/MIT
