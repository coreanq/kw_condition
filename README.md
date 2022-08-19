## *사용상 부주의로 인한 책임은 사용자에게 있습니다*
# kw_condition
 - [키움증권 조건검색 유튜브 가이드](https://www.youtube.com/watch?v=THCpQya4bXE&t=189s&ab_channel=%EC%B0%BD%EC%9B%90%EA%B0%9C%EB%AF%B8TV)

## 개발 환경  
 - Windows 10 
 - [Python 3.9.13 32bit]
 - [키움증권 Open API+](https://www1.kiwoom.com/nkw.templateFrameSet.do?m=m1408000000)  
 - 파이썬 패키지 관리툴 poetry 로 패키지 자동 설치 ([가이드](https://blog.gyus.me/2020/introduce-poetry/))
 

 ## 개발 문서  
 - [키움 오픈 API pdf 매뉴얼](https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.5.pdf)

## 참고 소스 
 - from https://github.com/sculove/QWebview-plus
 - from https://github.com/elbakramer/koapy


## 종속 패키지 설치 
~~~~
> poetry install
~~~~

## 사용 방법

### 0. python 실행 경로 확인 
    - python 가상 환경을 사용 중이라면 가상 환경의 path 가 맞는지 확인한다. 



```python
%gui qt5
%matplotlib inline

import matplotlib.pyplot as plt
import pandas as pd

import sys
print(sys.executable)
```

    d:\1git\kw_condition\.venv\Scripts\python.exe
    

### 1. 객체 생성


```python
from kw_condition import KiwoomOpenApiPlus
from kw_condition.utils import common_util

from PySide2.QtWidgets import QApplication

myApp = None
if isinstance(QApplication.instance(), type(None)):
    print('make instance')
    myApp = QApplication([])
else:
    print("use already")
    myApp = QApplication.instance()

kw_obj = KiwoomOpenApiPlus()
```

    make instance
    

### 2. 서버접속
* 자동로그인이 설정되어 있는 경우 로그인이 자동으로 처리 되며, 그렇지 않은 경우 팝업 창에서 수동으로 아이디, 비밀번호 정보를 입력해야함 
- TODO
    * 자동 로그인 설정되지 않은 상태서 로그인 정보를 외부에서 입력한 경우 매크로로 자동처리 할수 있도록 해야함 pywinauto


```python
kw_obj.tryConnect()
common_util.process_qt_events(kw_obj.isConnected, 60)
```

    * 16:51:24.400966 tryConnect 
    * 16:51:36.109315 _OnEventConnect 0
    * 16:51:36.122145 connected_entered 
    account count: 1, keyboard_boan: 1, firewall: 2
    

### 3. 서버 접속 상태 확인 


```python
kw_obj.isConnected()
```




    True



### 4. TR (주식기본정보요청) - Single Data

아래 처럼 직접 TR 요청에 필요한 입력값을 설정해 요청하고, 이후 들어오는 이벤트 또한 직접 처리해주는 방식으로 사용할 수 있다.


```python
rqname = '주식기본정보요청'
trcode = 'opt10001'
screen_no = '0001'  # 화면번호, 0000 을 제외한 4자리 숫자 임의로 지정, None 의 경우 내부적으로 화면번호 자동할당

inputs = {'종목코드': '005930'}

kw_obj.add_transaction(rqname, trcode, inputs, screen_no)

common_util.process_qt_events(kw_obj.has_transaction_result(rqname), 5)

# TR result 를 get 해야 다시 동일 rqname 으로 재요청 가능함 
print( kw_obj.get_transaction_result(rqname) )

```

    * 16:51:36.305282 request_transaction  {'rqname': '주식기본정보요청', 'trcode': 'opt10001', 'screen_no': '0001', 'inputs': {'종목코드': '005930'}}
    * 16:51:36.375981 _OnReceiveTrData  sScrNo: 0001, rQName: 주식기본정보요청, trCode: opt10001, recordName: , prevNext 0
    ['005930', '+78500', '-42300', '60400']
    

### 4. TR(주식일봉차트조회요청) - Multi Data  


```python
import datetime

rqname = '주식일봉차트조회요청'
trcode = 'opt10081'
screen_no = '0002'  # 화면번호, 0000 을 제외한 4자리 숫자 임의로 지정, None 의 경우 내부적으로 화면번호 자동할당

current_time_str = datetime.datetime.now().strftime('%Y%m%d')

inputs = {'종목코드': '005930', '기준일자' : current_time_str, "수정주가구분": '1'}

kw_obj.add_transaction(rqname, trcode, inputs, screen_no)

common_util.process_qt_events(kw_obj.has_transaction_result(rqname), 5)

# result 를 get 해야 다시 동일 rqname 으로 재요청 가능함 
daily_dict = kw_obj.get_transaction_result(rqname)
#print(daily_dict)




```

    * 16:51:40.144498 request_transaction  {'rqname': '주식일봉차트조회요청', 'trcode': 'opt10081', 'screen_no': '0002', 'inputs': {'종목코드': '005930', '기준일자': '20220818', '수정주가구분': '1'}}
    * 16:51:40.214232 _OnReceiveTrData  sScrNo: 0002, rQName: 주식일봉차트조회요청, trCode: opt10081, recordName: , prevNext 2
    

### 4. TR(주식일봉차트조회요청) - Multi Data - 차트 출력  


```python
import mplfinance as mpf

daily_df = pd.DataFrame.from_dict( daily_dict, orient='index', columns=["StockCode", "Date", "Open", "High", "Low", "Close", "Volume"])

# 일봉 조회의 경우 종목 코드가 2번째 row 부터 공백이므로 삭제 
daily_df.drop(columns='StockCode', axis =1, inplace = True)

# string date -> datetime 
daily_df['Date'] = pd.to_datetime( daily_df['Date'], format = '%Y%m%d') 

# str to int
selected_cols = ["Open", "High", "Low", "Close", "Volume"]
daily_df[ selected_cols ] = daily_df[selected_cols].astype('int')

daily_df = daily_df.set_index('Date')

daily_df = daily_df.sort_values(by= 'Date')

print(daily_df.head(5))

# 5, 10 , 20 , 60 일 평균 선 추가 
mpf.plot(daily_df, type='candle', mav=(5, 10, 20, 60), volume= True)


```

                 Open   High    Low  Close    Volume
    Date                                            
    2020-03-17  46900  49650  46700  47300  51218151
    2020-03-18  47750  48350  45600  45600  40152623
    2020-03-19  46400  46650  42300  42950  56925513
    2020-03-20  44150  45500  43550  45400  49730008
    2020-03-23  42600  43550  42400  42500  41701626
    

    d:\1git\kw_condition\.venv\lib\site-packages\mplfinance\_arg_validators.py:36: UserWarning: 
    
     ================================================================= 
    
       WARNING: YOU ARE PLOTTING SO MUCH DATA THAT IT MAY NOT BE
                POSSIBLE TO SEE DETAILS (Candles, Ohlc-Bars, Etc.)
       For more information see:
       - https://github.com/matplotlib/mplfinance/wiki/Plotting-Too-Much-Data
       
       TO SILENCE THIS WARNING, set `type='line'` in `mpf.plot()`
       OR set kwarg `warn_too_much_data=N` where N is an integer 
       LARGER than the number of data points you want to plot.
    
     ================================================================ 
      warnings.warn('\n\n ================================================================= '+
    


    
![png](readme-01.png)
    


### 4. TR(주식일봉차트조회요청) - Multi Data - 연속 조회 


```python

```

### 5. 조건 검색 (사용자 설정 조건 리스트 읽기 from HTS)
이후 예시의 정상동작을 위해서는 아래에서 사용되는 조건들과 같은 이름을 가지는 조건들이 미리 저장되어 있어야 한다.

참고로 조건들을 편집하고 저장하는건 영웅문 HTS 내부에서만 가능하기 때문에 따로 HTS 를 열어 편집해주어야 한다.


```python
kw_obj.load_condition_names()
common_util.process_qt_events(kw_obj.has_condition_names, 5)
print( kw_obj.get_condition_names() )

```

    * 16:51:41.868258 _OnReceiveConditionVer  ret: 1, msg: [OK] 사용자 조건검색식 읽기
    {'장초반': 1, '휴식': 2, '장후반': 0, '이탈3': 4, '이탈15': 6, '새조건명': 3, '새조건명2': 5}
    

### 5. 조건검색 (사용자 조건과 일치하는 종목 리턴)


```python
condition_name = '장초반'
kw_obj.request_condition(condition_name)
common_util.process_qt_events(kw_obj.has_condition_names, 5)


```

    * 16:51:50.798102 _OnReceiveTrCondition  scrNo: 0010, codeList: 002140;005930;063170;107600;, conditionName: 장초반 index: 1, next: 0
    condition list add: 002140 
    condition list add: 005930 
    condition list add: 063170 
    condition list add: 107600 
    

### 6. 실시간 조건 검색 

### 7. 주문 처리


