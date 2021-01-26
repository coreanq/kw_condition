# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'mainwindow.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(429, 207)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayout = QtWidgets.QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btnRealInfoEnabled = QtWidgets.QPushButton(self.centralwidget)
        self.btnRealInfoEnabled.setObjectName("btnRealInfoEnabled")
        self.horizontalLayout.addWidget(self.btnRealInfoEnabled)
        self.btnMakeExcel = QtWidgets.QPushButton(self.centralwidget)
        self.btnMakeExcel.setObjectName("btnMakeExcel")
        self.horizontalLayout.addWidget(self.btnMakeExcel)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.btnYupjong = QtWidgets.QPushButton(self.centralwidget)
        self.btnYupjong.setObjectName("btnYupjong")
        self.horizontalLayout_2.addWidget(self.btnYupjong)
        self.btnCondition = QtWidgets.QPushButton(self.centralwidget)
        self.btnCondition.setObjectName("btnCondition")
        self.horizontalLayout_2.addWidget(self.btnCondition)
        self.gridLayout.addLayout(self.horizontalLayout_2, 1, 0, 1, 1)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.btnJango = QtWidgets.QPushButton(self.centralwidget)
        self.btnJango.setObjectName("btnJango")
        self.horizontalLayout_3.addWidget(self.btnJango)
        self.btnChegyeol = QtWidgets.QPushButton(self.centralwidget)
        self.btnChegyeol.setObjectName("btnChegyeol")
        self.horizontalLayout_3.addWidget(self.btnChegyeol)
        self.gridLayout.addLayout(self.horizontalLayout_3, 2, 0, 1, 1)
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.lineCmd = QtWidgets.QLineEdit(self.centralwidget)
        self.lineCmd.setObjectName("lineCmd")
        self.horizontalLayout_4.addWidget(self.lineCmd)
        self.btnRun = QtWidgets.QPushButton(self.centralwidget)
        self.btnRun.setObjectName("btnRun")
        self.horizontalLayout_4.addWidget(self.btnRun)
        self.gridLayout.addLayout(self.horizontalLayout_4, 3, 0, 1, 1)
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 429, 26))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "Automated st"))
        self.btnRealInfoEnabled.setText(_translate("MainWindow", "실시간 정보 Enabled"))
        self.btnMakeExcel.setText(_translate("MainWindow", "체결 정보 엑셀 생성"))
        self.btnYupjong.setText(_translate("MainWindow", "정보요청(업종)"))
        self.btnCondition.setText(_translate("MainWindow", "조건진입리스트"))
        self.btnJango.setText(_translate("MainWindow", "정보요청(잔고)"))
        self.btnChegyeol.setText(_translate("MainWindow", "정보요청(체결)"))
        self.btnRun.setText(_translate("MainWindow", "실행"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())

