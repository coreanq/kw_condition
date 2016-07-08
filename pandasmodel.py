import sys
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt5.QtCore import QVariant
from main_util import whoami
import PyQt5.QtCore as QtCore


class PandasModel(QtCore.QAbstractTableModel):
    """
    Class to populate a table view with a pandas dataframe
    """
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self._data = data
        self._roleNames = {}

    def __len__(self):
        return len(self._data)

    def __str__(self):
        return str(self._data)

    def rowCount(self, parent=None):
        return len(self._data.values)

    def columnCount(self, parent=None):
        return self._data.columns.size

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            if(role==QtCore.Qt.DisplayRole):
                return self._data.values[index.row()][index.column()]
            else:
                # self._roleName 은 QHash(int, QByteArray)
                columnName = self._roleNames[role].data().decode('utf8')
                print('row {} col {} role {} columnName {} '.format(index.row(), index.column(), role, columnName))
                print(self._data.at[index.row(), columnName])
                return self._data.at[index.row(), columnName]
        return QVariant()

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._data.columns[col]
        return None
        
    # return 값은 QHash(int, QByteArray)
    def roleNames(self):
        for index, name in enumerate(self._data.columns):
            self._roleNames[ QtCore.Qt.UserRole + index + 1] = QtCore.QByteArray(name.encode())
        return self._roleNames
        
        
    def refresh(self):
        leftTopIndex = self.index(0, 0)
        print("%s row count %s col count %s" % ( whoami(), self.rowCount(), self.columnCount() ))
        rightBottomIndex = self.index(self.rowCount(), self.columnCount())
        self.dataChanged.emit(leftTopIndex, rightBottomIndex)
        
    def _dataFrame(self):
        return self._data


   

if __name__ == '__main__':

    # pandas model test
    import pandas as pd
    df = pd.DataFrame(columns=('code', 'name'))
    model = PandasModel(df)
    print(model.headerData(0, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole))
    print("%s %s" % (id(df),  id(model._dataFrame())))
    print("before append model length %s" %(len(model)))
    df.loc[len(df)] = ['1', '1111']
    df.loc[len(df)] = ['2', '2222']
    df.loc[len(df)] = ['3', '3333']
    df.loc[len(df)] = ['4', '4444']
    index = model.index(0, 0)
    # print("0 row 0 col data is %s" % (model.data(index)))
    model.refresh()
    print("after append model length %s" %(len(model)))
    print("model list is \n %s " % model)
    print("model roleNames %s" % model.roleNames())
    
    # pandas model and qml operation test
    from PyQt5.QtQml import QQmlApplicationEngine
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl
    myApp = QApplication(sys.argv)
        
    qmlEngine = QQmlApplicationEngine()
    rootContext = qmlEngine.rootContext()
    rootContext.setContextProperty("cppModelCondition", model)
    qmlEngine.load(QUrl('main.qml'))
    sys.exit(myApp.exec_())
    # input()