import QtQuick 2.6
import QtQuick.Controls 1.4

ApplicationWindow {
    id: main
    visible: true
    title: "automated st"
    width: 400
    height: 180
    signal startClicked()
    signal restartClicked()
    signal requestJangoClicked()
    signal chegyeolClicked()
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
                text: "재시작"
                Rectangle{
                    anchors.fill: parent
                    color: "red"
                    opacity: 0.5
                }
                onClicked: {
                    console.log('stopClicked')
                    main.restartClicked()
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
                id: btnChegyeol
                width: parent.width/grid.columns
                text: "체결내역"
                onClicked: {
                    console.log('chegyeolClicked')
                    main.chegyeolClicked()
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
    onClosing: {
        console.log('make jango info before closing')
        main.testClicked('test_make_jangoInfo()')
    }


}

