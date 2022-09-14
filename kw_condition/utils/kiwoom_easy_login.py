from pywinauto.application import Application
from pywinauto import clipboard as Clipboard
import pandas as pd
import time

# 키움 easy stater 실행 
# for inspector.exe use uia
# app = Application(backend="uia").start('C:/KiwoomEasy/bin/nkeasystarter.exe')

# # find dialog
# main_dlg = app.window( best_match= '영웅문 EASY Login')
# main_dlg.wait( wait_for = 'exists' )
# # 이작업을 통해 타겟이 되는 컨트롤을 찾아야 함 
# main_dlg.print_control_identifiers()

# edit_controls = [ main_dlg.Edit1, main_dlg.Edit2, main_dlg.Edit3 ]
# user_inputs = [user_id, user_pass, user_cert]

# for infos in zip(edit_controls, user_inputs):
#     child_control = infos[0]
#     child_control.double_click_input( button = 'left' ) # 더블클릭으로 기존 입력을 selecting 해서 지워지게 함 
#     child_control.type_keys( infos[1] ) # shoule use instead of set_text 

# login_btn_control = main_dlg.Button1
# login_btn_control.click_input( button = 'left' )

# TODO: 업그레이드 확인 창 처리 


# find dialog
# time.sleep(5)


# 왼쪽 하단의 뉴스 다이얼로는 Pane25 임 
app = Application(backend="uia").connect( path = 'nkeasy.exe' )

# find dialog
main_dlg = app.영웅문EASY
main_dlg.wait( wait_for = 'exists', timeout = 5 ) # not for 'visible'

# 이작업을 통해 타겟이 되는 컨트롤을 찾아야 함 
# main_dlg.print_control_identifiers()

# 우하단 패널 
target_window = main_dlg.Pane25

# target_window.print_control_identifiers()

# 뉴스 탭 클릭 
target_window.뉴스TabIItem.click_input( button = 'left')

# 전체 라디오 박스 클릭 
target_window.전체Button.click_input( button = 'left')

# 마우스 우클릭 해서 context 메뉴 보이고
target_window.click_input( button = 'right')

# 'z' 키 눌러서 클립보드 복사 
target_window.type_keys('z')

clipboard_data = print( Clipboard.GetData() )


df = pd.read_clipboard()

nan_filter = df['CODE'].isna()

df = df.dropna( subset = ['CODE'] ).reset_index() 

print( df ) 





print( 'done' ) 



