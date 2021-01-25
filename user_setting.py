# -*-coding: utf-8 -

AUTO_TRADING_OPERATION_TIME = [ [ [9, 0], [15, 19] ] ]  # 매도호가 정보의 경우 동시호가 시간에도  올라오므로 주의

# 조건검색식 적용시간
CONDITION_INFO = {
    "장초반": {
        "start_time": {
            "hour": 8, 
            "minute": 5, 
            "second": 0, 
        },
        "end_time": {
            "hour": 15, 
            "minute": 0, 
            "second": 0, 
        }
    }
}

MAESU_UNIT = 5000000 # 매수 기본 단위 

BUNHAL_MAESU_LIMIT = 3 # 분할 매수 횟수 제한 

MAX_STOCK_POSSESION_COUNT = 1 # 제외 종목 리스트 불포함한 최대 종목 보유 수

STOP_LOSS_CALCULATE_DAY = 1   # 최근 ? 일간 특정 가격 기준으로 손절 계산

REQUEST_MINUTE_CANDLE_TYPE = 3  # 운영중 요청할 분봉 종류

MAX_SAVE_CANDLE_COUNT = (STOP_LOSS_CALCULATE_DAY +1) * 140 # 3분봉 기준 저장 분봉 갯수 

MAESU_TOTAL_PRICE =         [ MAESU_UNIT * 1,                   MAESU_UNIT * 1,                     MAESU_UNIT * 1,                     MAESU_UNIT * 1]
# 추가 매수 진행시 stoploss 및 stopplus 퍼센티지 변경
# 추가 매수 어느 단계에서든지 손절금액은 확정적이여야 함 
# 세금 수수료 별도 계산  
BASIC_STOP_LOSS_PERCENT = -0.6
STOP_PLUS_PER_MAESU_COUNT = [  10,                             10,                                 10,                                 10           ] 
STOP_LOSS_PER_MAESU_COUNT = [  BASIC_STOP_LOSS_PERCENT,        BASIC_STOP_LOSS_PERCENT,            BASIC_STOP_LOSS_PERCENT,            BASIC_STOP_LOSS_PERCENT ]

EXCEPTION_LIST = ['035480'] # 장기 보유 종목 번호 리스트  ex) EXCEPTION_LIST = ['034220'] 

###################################################################################################
TEST_MODE = False    # 주의 TEST_MODE 를 True 로 하면 1주 단위로 삼o 


###################################################################################################
# for slack  bot
SLACK_BOT_ENABLED = True
SLACK_BOT_TOKEN = ""
SLACK_BOT_CHANNEL = ""

###################################################################################################
# for google spread
GOOGLE_SPREAD_AUTH_JSON_FILE = 'kiwoom_charles_auth.json'
GOOGLE_SPREAD_SHEET_NAME = 'kw3_trade'