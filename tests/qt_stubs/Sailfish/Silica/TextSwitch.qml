import QtQuick 2.6

// The SDK TextSwitch writes checked on click unless automaticCheck is disabled.
Item {
    property string text: ""
    property bool checked: false
    property bool automaticCheck: true
    signal clicked()
    onClicked: if (automaticCheck) checked = !checked
}
