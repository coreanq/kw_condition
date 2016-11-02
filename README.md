## *사용상 부주의로 인한 책임은 사용자에게 있습니다*
# kw_condition
 - 키움 오픈 API + PyQt5 를 사용하여 console 형식으로 주식 매매를 자동으로 수행하는 프로그램
 - 키움증권의 조건 검색 기능을 이용하여 조건 검색에 해당하는 종목리스트를 얻어와 매매 수행
 - 현재는 하루에 모든 매매를 끝내는 단타로 구현
 - <a href="https://www.youtube.com/watch?v=QnnO4kIj51c" target="_blank"><img src="http://img.youtube.com/vi/YOUTUBE_VIDEO_ID_HERE/0.jpg" 
alt="키움증권 조건검색 사용 가이드" width="240" height="180" border="10" /></a>

## 개발 환경  
 - Windows 32bit 권장
 - [키움증권 Open API+](https://www1.kiwoom.com/nkw.templateFrameSet.do?m=m1408000000)
 - [Python Anaconda 4.2.0 (python 3.5) 32bit](https://www.continuum.io/downloads#windows)
 - [PyQt 5.7.0 32bit](https://www.riverbankcomputing.com/software/pyqt/download5)
 - [키움 오픈 API](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.1.pdf)

## 참고 소스 
 - from https://github.com/sculove/QWebview-plus

## 사용 예
~~~~
 > python main.py 
~~~~

> main.py 내의 변수 설정 내용 
> STOCK_TRADE_TIME = [ [ [9, 5], [15, 10] ]] #해당 시스템 동작 시간 설정 -->  9시 5분 부터 15시 10분까지만 동작
> CONDITION_NAME = '급등' #키움증권 HTS 에서 설정한 조건 검색 식 이름

> TEST_MODE = True    # 주의 TEST_MODE 를 False 로 하는 경우, TOTAL_BUY_AMOUNT 만큼 구매하게 됨  
> TOTAL_BUY_AMOUNT = 50000000 #  매도 호가1, 매도 호가 2의 총 수량이 5000만원 이상 안되면 매수금지  (슬리피지 최소화)
>
> TIME_CUT_MIN = 20 # 타임컷 분값으로 해당 TIME_CUT_MIN 분 동안 가지고 있다가 시간이 지나면 손익분기점으로 손절가를 올림 
> STOP_PLUS_PERCENT = 3.5 # 익절 퍼센티지 
> STOP_LOSS_PERCENT = 2.5 # 손절 퍼센티지  
> STOCK_PRICE_MIN_MAX = { 'min': 2000, 'max':50000} #조건 검색식에서 오류가 끔 발생하므로 매수 범위 가격 입력


## License
Licensed under MIT:

https://opensource.org/licenses/MIT
