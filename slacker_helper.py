import sys
import user_setting
from slacker import Slacker

# for slack bot
token = user_setting.SLACK_BOT_TOKEN
slack = Slacker(token)

def post_message(message):
    slack.chat.post_message(channel=user_setting.SLACK_BOT_CHANNEL, text=message, as_user=True)

if __name__ == "__main__":

    test_message = ''
    if( len(sys.argv) == 2 ):
        test_message = sys.argv[1]
    else:
        test_message = '테스트메시지 ------------------------------------------------------------------------------------------------------------------'
    post_message( '*{}* --------------------------------------------------------------------------------------------------------------------------------------'.format(test_message))