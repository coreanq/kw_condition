import QtQuick 2.5
import QtQuick.Controls 1.4
import QtQuick.Layouts 1.3
import "debugModule.js" as testHarness



Rectangle {
    id: main
    width: 640
    height: 480
    clip: false
    color: 'white'

    ListView {
        id: viewJogun
        width: 205
        anchors.top: parent.top
        anchors.topMargin: 0
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 0
        anchors.left: parent.left
        anchors.leftMargin: 0
        model: if(testHarness.isDebug() == true ){
            return modelDummy;
        }
        else{
            return cppModelCondition;
        }
        delegate: myDelegate
        
        Component {
          id: myDelegate
          Rectangle{ 
              color: "yellow"

                  Text { 
                      anchors.fill: parent
                      text: code }
                //   Text { text: name }

          }
          
        }
    }

    ListView {
        id: viewJongmok
        anchors.left: viewJogun.right
        anchors.leftMargin: 0
        anchors.top: parent.top
        anchors.topMargin: 0
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 0
        anchors.right: parent.right
        anchors.rightMargin: 0
        model: ListModel {
            ListElement {
                name: "Grey"
                colorCode: "grey"
            }

            ListElement {
                name: "Red"
                colorCode: "red"
            }

            ListElement {
                name: "Blue"
                colorCode: "blue"
            }

            ListElement {
                name: "Green"
                colorCode: "green"
            }
        }
    }

}
