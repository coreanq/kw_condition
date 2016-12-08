import QtQuick 2.7
import QtQuick.Controls 2.0

ApplicationWindow {
    id: main
    visible: true
    title: "automated st"
    width: 200
    height: 180
    signal startClicked()
    signal stopClicked()
    signal requestJangoClicked()
    signal testClicked(string arg)

    Column {
        anchors.fill: parent
        spacing: 2
        Grid{
            id: grid
            width: parent.width
            columns: 2
            spacing: 2
            Button{
                id: btnStart
                width: parent.width/grid.columns
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
                width: parent.width/grid.columns
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
                width: parent.width/grid.columns
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
            Button {
                id: btnExecute
                width: parent.width/grid.columns
                text: "함수 실행"
                onClicked: {
                    console.log(txtTest.text)
                    main.testClicked(txtTest.text)
                }
            }
        }
        TextEdit{
            id: txtTest
            width: parent.width
            height: 100
            focus: true
            wrapMode: TextEdit.Wrap
            font.pointSize: 16
            Rectangle {
                anchors.fill: parent
                color: "light gray"
                opacity: 0.5
            }
        }
    }


}

