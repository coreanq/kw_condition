# -*- coding: utf-8 -*-
import math

'''   
Q : 화면번호는 어떤역할을 하는지요?

A : 사용자 입장에서는 영웅문4의 화면번호와 동일한 맥락이라고 보시면 되겠습니다.
    시스템적으로 화면번호는 데이터 송수신 및 실시간데이터의 키값으로 사용됩니다.
    하나의 화면번호에 특정 종목의 실시간시세가 등록되어 수신되고 있는 상태에서
    해당 화면번호를 다른 용도로 다시 사용하거나 종목을 바꾸어 데이터 요청에 사용하는 경우
    해당 화면번호에 등록되어 있던 종목은 자동으로 실시간시세 해지가 됩니다.
    
    가령 화면번호 1111을 사용하여 이미 A종목의 실시간시세를 수신하고 있는 상태에서
    1111 화면번호로 B종목의 시세데이터를 조회하는 경우 A종목의 실시간시세는 자동으로 해지되고
    1111 화면번호로 B종목의 실시간시세가 등록되어 수신됩니다.

    OpenAPI는 사용자가 화면번호를 임의로 지정할 수 있어서
    어떤 화면번호에 어떤 데이터를 요청/수신 할지 관리하실 수 있습니다.
    화면번호는 몇가지 규칙을 지켜주시면서 임의의 값으로 지정하여 사용하시면 됩니다.
    1. 4자릿수 숫자 사용 "1111", "1234",,,
    2. 프로그램내 화면번호 최대 사용갯수는 200개. 동일한 화면번호 재사용 가능
    (영웅문4 에서 화면을 200개까지 열수 있는 개념으로 이해하시면 되겠습니다.)
    3. 동일한 화면번호를 연속적으로 반복하여 사용하지 않도록 운영하시면 됩니다.
    데이터 요청시, 주문전송시 화면번호를 생략할 수 없습니다.

'''

# 실시간 체결 화면번호
# 실시간 잔고의 경우 체결시 콜백함수를 이용해야 하며 실시간 잔고로는 잔고 조회가 안됨  

send_order_value = {
    "신규매수" : 1,
    "신규매도" : 2,
    "매수취소" : 3,
    "매도취소" : 4,
    "매수정정" : 5,
    "매도정정" : 6,
    "지정가"   : "00",
    "시장가"   : "03",
    "조건부지정가" : "05",
    "최유리지정가" : "06",
    "최우선지정가" : "07",
    "지정가IOC"    : "10",
    "시장가IOC"    : "13",
    "최유리IOC"    : "16",
    "지정가FOK"    : "20",
    "시장가FOK"    : "23",
    "최유리FOK"    : "26",
    "장전시간외종가": "61",
    "시간외단일가매매": "62",
    "장후시간외종가": "81"
}

# 저장시 필요한 리스트만 나열한 것임
'''
    [실시간 데이터 - 주의사항]
    실시간 타입 "주문체결", "잔고", "파생잔고"는 주문관련 실시간 데이터를 전달하기 때문에 시세조회한 뒤나 SetRealReg()함수로 등록해서 사용할 수 없습니다.
    이 실시간 타입은 주문을 해야 발생하며 주문전용 OnReceiveChejanData()이벤트로 전달됩니다.

    아래 실시간 타입은 시스템 내부용으로 사용할수없는 실시간 타입입니다.
    1. 임의연장정보
    2. 시간외종목정보
    3. 주식거래원
    4. 순간체결량
    5. 선물옵션합계
    6. 투자자별매매
'''



# 종목 코드는 공통이믈 반드시 포함하도록 함 
tr_column_info = {
    #주식기본정보 요청 
    'opt10001': ( 
        '종목코드', '상한가', '하한가', '기준가'
    ),
    "opt10081": (
        '종목코드', '현재가', '거래량', '시가', '고가', '저가', '일자'
    ),

}
get_comm_data_info = {
    # 체결 정보는 파일에 저장됨
    "체결정보": (
        '수익율', '수익', '매수횟수', '주문타입', # 원래 없는 멤버
        '종목코드', '주문구분', '체결가', '체결량', '주문/체결시간', '종목명'),

    'TR:계좌평가잔고내역요청': (
        '종목명', '종목번호', #'평가손익', '수익률(%)', --> 실시간 잔고 기능 사용시 계속 잔고 요청해야하므로 삭제
        '매입가', '전일종가', '보유수량',
        '매매가능수량', '현재가' # '세금'
    ),
    "TR:업종분봉": (
        "현재가", "체결시간"
    ),
    "TR:분봉": (
        "현재가", "거래량", "체결시간", "시가", "고가", "저가"
    ),
    "TR:기본정보": (
        "상한가", "하한가", "기준가"
    ),
    'TR:계좌평가현황': (
        '예수금', 'D+2추정예수금', '유가잔고평가액', '예탁자산평가액', '총매입금액', '추정예탁자산'
    ),
    'TR:체결잔고': (
        '예수금','예수금D+1','예수금D+2', '출금가능금액', '20주문가능금액', '30주문가능금액', '40주문가능금액', '50주문가능금액', '60주문가능금액','100주문가능금액'
    ),

    "실시간-주식체결":(
        "체결시간",
        "현재가",
        "등락율",
        "(최우선)매도호가",
        "(최우선)매수호가",
        "거래량",   # 체결시 거래량 
        "누적거래량",
        "시가",
        "고가",
        "저가",
        "체결강도",
        '전일거래량대비(비율)'
    ),
    "실시간-주식호가잔량": (
        '호가시간',
        '매도호가수량1',
        '매도호가수량2',
        '매수호가수량1',
        '매수호가수량2',
        "매도호가총잔량", 
        "매수호가총잔량" 
    ),
    '실시간-업종지수': (
        '체결시간',
        '현재가',
        '등락율',
        '전일대비기호',
        '시가',
        '고가',
        '저가'
    ),
    '실시간-주식당일거래원':(
        # "외국계매도추정합",
        # "외국계매도추정합변동",
        # "외국계매수추정합",
        # "외국계매수추정합변동",
        # "외국계순매수추정합",
        # "외국계순매수변동",
        # "거래소구분",
        '매도거래원1',
        '매도거래원2',
        '매도거래원3',
        '매도거래원4',
        '매도거래원5',
        '매수거래원1',
        '매수거래원2',
        '매수거래원3',
        '매수거래원4',
        '매수거래원5'
    ),
    '실시간-장시작시간':(
        '장운영구문',
        '체결시간',
        '장시작예상잔여시간'
    )
}
# fid 는 다 넣을 필요 없음
# 거래원데이터는 실시간으로 제공되지 않는 데이터여서 해당 fid값을 SetRealReg에 추가하셔도 수신되지 않습니다. from 운영자
# OpenAPI는 증거금이나 예수금, 잔고손익 을 실시간으로 제공하지 않습니다 from 운영자
type_fidset = {
    "주식시세": "10;11;12;27;28;13;14;16;17;18;25;26;29;30;31;32;311",
    "잔고": "9201;9001;10;930;931;932;933;951;8019",
    "주식거래원": "9001;9026;302;334;20;203;207;210;211;337",
    # "주식체결": "20;10;11;12;27;28;15;13;14;16;17;18;25;26;29;30;31;32;228;311;290;691",
    "주식체결": "20;10;12;27;28;15;13;16;17;18;30",
    "주식호가잔량":"21;61;62;71;72;121;125",
    '업종지수': "20;10;11;12;16;17;18;25;26",
    '장시작시간': "215;20;214",
    "주식종목정보": "305;306;307;382;370"
}
name_fid = {
    '호가시간': 21,
    '매도호가1': 41,
    '매도호가수량1': 61,
    '매수호가1': 51,
    '매수호가수량1': 71,
    '매도호가2': 42,
    '매도호가수량2': 62,
    '매수호가2': 52,
    '매수호가수량2': 72,
    '매도호가3': 43,
    '매도호가수량3': 63,
    '매수호가3': 53,
    '매수호가수량3': 73,
    '매도호가4': 44,
    '매도호가수량4': 64,
    '매수호가4': 54,
    '매수호가수량4': 74,
    '매도호가5': 45,
    '매도호가수량5': 65,
    '매수호가5': 55,
    '매수호가수량5': 75,
    '매도호가총잔량': 121,
    '매수호가총잔량': 125,
    '누적거래량': 13,

    '매도거래원1': 141,
    '매도거래원수량1': 161,
    '매도거래원별증감1': 166,
    '매도거래원코드1': 146,
    '매수거래원1': 151,
    '매수거래원수량1': 171,
    '매수거래원별증감1': 176,
    '매수거래원코드1': 156,

    '매도거래원2': 142,
    '매도거래원수량2': 162,
    '매도거래원별증감2': 167,
    '매도거래원코드2': 147,
    '매수거래원2': 152,
    '매수거래원수량2': 172,
    '매수거래원별증감2': 177,
    '매수거래원코드2': 157,

    '매도거래원3': 143,
    '매도거래원수량3': 163,
    '매도거래원별증감3': 168,
    '매도거래원코드3': 148,
    '매수거래원3': 153,
    '매수거래원수량3': 173,
    '매수거래원별증감3': 178,
    '매수거래원코드3': 158,

    '매도거래원4': 144,
    '매도거래원수량4': 164,
    '매도거래원별증감4': 169,
    '매도거래원코드4': 149,
    '매수거래원4': 154,
    '매수거래원수량4': 174,
    '매수거래원별증감4': 179,
    '매수거래원코드4': 159,

    '매도거래원5': 145,
    '매도거래원수량5': 165,
    '매도거래원별증감5': 170,
    '매도거래원코드5': 150,
    '매수거래원5': 155,
    '매수거래원수량5': 175,
    '매수거래원별증감5': 180,
    '매수거래원코드5': 160,

    "외국계매도추정합": 261,
	"외국계매도추정합변동": 262,
	"외국계매수추정합": 263,
	"외국계매수추정합변동": 264, 
	"외국계순매수추정합": 267,
	"외국계순매수변동": 268, 
	"거래소구분": 337,

    "계좌번호": 9201,
    "주문번호": 9203,
    "관리자사번": 9205,
    "종목코드": 9001,
    "주문업무분류": 912,  # (JJ:주식주문, FJ:선물옵션, JG:주식잔고, FG:선물옵션잔고)
    "주문상태": 913,
    "종목명": 302,
    "주문수량": 900,
    "주문가격": 901,
    "미체결수량": 902,
    "체결누계금액": 903,
    "원주문번호": 904,
    "주문구분": 905, # (+현금내수,-현금매도…)
    "매매구분": 906,  # (보통,시장가…)
    "매도매수구분": 907, #(1:매도,2:매수)
    "주문/체결시간": 908,
    "체결번호": 909,
    "체결가": 910,
    "체결량": 911,
    "현재가": 10,
    "(최우선)매도호가": 27,
    "(최우선)매수호가": 28,
    "단위체결가": 914,
    "단위체결량": 915,
    "당일매매수수료": 938,
    "당일매매세금": 939,
    "거부사유": 919,
    "화면번호": 920,
    "921": 921,
    "922": 922,
    "923" : 923,
    "924" : 924,
    "신용구분": 917,
    "대출일": 916,
    "보유수량": 930,
    "매입단가": 931,
    "총매입가": 932,
    "주문가능수량": 933,
    "당일순매수수량": 945,
    "매도/매수구분":  946,
    "당일총매도손실": 950,
    "예수금": 951,
    "담보대출수량": 959,
    "기준가": 307,
    "손익율": 8019,
    "신용금액": 957,
    "신용이자": 958,
    "만기일": 918,
    "당일실현손익(유가)": 990,
    "당일실현손익률(유가)": 991,
    "당일실현손익(신용)": 992,
    "당일실현손익률(신용)":  993,
    "파생상품거래단위": 397,
    "상한가":   305,
    "하한가": 306,
    "기준가": 307,
    "체결강도": 228,

    "등락율": 12, 
    "체결시간": 20,
    "전일대비기호":   25,
    '전일대비': 11,
    '거래량': 15,
    '누적거래대금': 14,
    '시가': 16,
    '고가': 17,
    '저가': 18,
    '장구분': 290,
    '장운영구분': 215,
    '전일거래량대비(비율)': 30,
    '전일거래량대비(계약,주)': 26
}

def parseErrorCode(code):
    """에러코드 메시지

        :param code: 에러 코드
        :type code: str
        :return: 에러코드 메시지를 반환

        ::

            kw_util.parseErrorCode("00310") # 모의투자 조회가 완료되었습니다
    """
    code = str(code)
    ht = {
        "0"    : "정상처리",            
        "-10"  : "실패",
        "-11"  : "조건번호 없음",                                                                
        "-12"  : "조건번호와 조건식 불일치",                                                     
        "-13"  : "조건검색 조회요청 초과",                                                       

        "-100" : "사용자정보교환에 실패하였습니다. 잠시후 다시 시작하여 주십시오.",
        "-101" : "서버 접속 실패",
        "-102" : "버전처리가 실패하였습니다.",
        "-103" : "개인방화벽 실패",
        "-104" : "메모리 보호 실패",
        "-105" : "함수 입력값 오류",
        "-106" : "통신 연결 종료",
        "-107" : "보안모듈 오류",                                                                 
        "-108" : "공인인증 로그인 필요",

        "-200" : "시세조회 과부하",
        "-201" : "REQUEST_INPUT_st Failed",
        "-202" : "요청 전문 작성 실패",
        "-203" : "데이터 없음",
        "-204" : "조회가능한 종목수 초과, 한번에 조회 가능한 종목 개수는 최대 100종목",
        "-205" : "데이터 수신 실패",
        "-206" : "조회가능한 FID수 초과. 한번에 조회 가능한 FID개수는 최대 100개.",               
        "-207" : "실시간 해제오류",                                                               
        "-209" : "시세조회제한",      

        "-300" : "주문 입력값 오류",
        "-301" : "계좌비밀번호를 입력하십시오.",
        "-302" : "타인계좌는 사용할 수 없습니다.",
        "-303" : "주문가격이 20억원을 초과합니다.",
        "-304" : "주문가격은 50억원을 초과할 수 없습니다.",
        "-305" : "주문수량이 총발행주수의 1%를 초과합니다.",
        "-306" : "주문수량은 총발행주수의 3%를 초과할 수 없습니다.",
        "-307" : "주문전송 실패",
        "-308" : "주문전송 과부하",
        "-309" : "주문수량 300계약 초과",
        "-310" : "주문수량 500계약 초과",                                                        
        "-311" : "주문전송제한 과부하",
        "-340" : "계좌정보 없음",                                                                
        "-500" : "종목코드 없음"
    }
    return ht[code] + " (%s)" % code if code in ht else code

def hogaUnitCalc(price,jang):
    hogaUnit = 1
    if price < 1000:
        hogaUnit = 1
    elif price < 5000:
        hogaUnit = 5
    elif price < 10000:
        hogaUnit = 10
    elif price < 50000:
        hogaUnit = 50
    elif price < 100000 and jang == "kospi":
        hogaUnit = 100
    elif price < 500000 and jang == "kospi":
        hogaUnit = 500
    elif price >= 500000 and jang == "kospi":
        hogaUnit = 1000
    elif price >= 50000 and jang == "kosdaq":
        hogaUnit = 100
    
    return hogaUnit

def getHogaPrice(currentPrice, hogadifference, jang):
    hogaPrice = currentPrice
    hogaunit = hogaUnitCalc(hogaPrice, jang)
    
    for _ in range(abs(hogadifference)):
        if hogadifference < 0: 
            minusV = (hogaPrice - 1)
            hogaunit = hogaUnitCalc(minusV, jang)
            mot = minusV // hogaunit
            hogaPrice = mot * hogaunit
        elif hogadifference > 0:
            hogaunit = hogaUnitCalc(hogaPrice, jang)
            hogaPrice = hogaPrice+ hogaunit
    
    mot = math.ceil(hogaPrice // hogaunit)
    hogaPrice = mot * hogaunit
    return int(hogaPrice)
