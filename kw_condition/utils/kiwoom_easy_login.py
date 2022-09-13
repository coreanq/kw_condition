
edit_id   = 1000
edit_pass = 1001
edit_cert = 1002
btn_login = 1


# 키움 easy 실행 
from pywinauto.application import Application
from pywinauto  import findwindows

app = Application(backend="uia").start('C:/KiwoomEasy/bin/nkeasystarter.exe')

# find dialog
main_dlg = app.window( best_match= '영웅문 EASY Login')
main_dlg.wait( wait_for = 'ready' )

control_ids = [edit_id, edit_pass, edit_cert ]
user_inputs = [user_id, user_pass, user_cert]

for infos in zip(control_ids, user_inputs):
    child_control = main_dlg.child_window( control_id = infos[0] )
    # child_control.print_control_identifiers()
    # child_control.wait( wait_for = 'ready')
    child_control.wrapper_object().double_click_input( button = 'left' ) # 더블클릭으로 기존 입력을 selecting 해서 지워지게 함 
    child_control.wrapper_object().type_keys( infos[1] ) # shoule use instead of set_text 

login_btn_control = main_dlg.child_window( control_id = btn_login )
login_btn_control.wrapper_object().click_input( button = 'left' )

# TODO: 업그레이드 확인 창 처리 


# find dialog

news_dlg_id = 59648

main_dlg = findwindows.find_element( control_id = news_dlg_id )
main_dlg.wait( wait_for = 'ready', timeout = 120 )

# child_control = main_dlg.child_window( control_id = news_dlg_id )
# child_control.print_control_identifiers()



print( 'done' ) 



