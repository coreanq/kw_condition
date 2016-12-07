import QtQuick 2.5
import QtQuick.Controls 2.0

ApplicationWindow {
    id: main
    visible: true
    title: "automated st"
    width: 200
    height: 80
    signal startClicked()
    signal stopClicked()
    signal requestJangoClicked()
    signal testClicked(string arg)

    Grid{
        anchors.fill: parent
        columns: 2
        spacing: 2
        Button{
            id: btnStart
            text: "시작"
            Rectangle{
                anchors.fill: parent
                color: "blue"
                opacity: 0.5
            }
            onClicked: {
                console.log('startClicked')
                main.startClicked()
            }

        }
        Button {
            id: btnStop
            text: "종료"
            Rectangle{
                anchors.fill: parent
                color: "red"
                opacity: 0.5
            }
            onClicked: {
                console.log('stopClicked')
                main.stopClicked()
            }


        }
        Button {
            id: btnRequestJango
            text: "정보요청"
            Rectangle{
                anchors.fill: parent
                color: "yellow"
                opacity: 0.5
            }
            onClicked: {
                console.log('requestJangoClicked')
                main.requestJangoClicked()
            }
        }
        Button{
            id: btnTest
            text: "테스트"
            onClicked: {
                console.log('testClicked')
                main.testClicked("dummy")
            }
        }
    }

}

