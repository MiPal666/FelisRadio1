import QtQuick 2.6
Item {
 property string path: ""
 property bool available: true
 property bool powered: false
 property bool connected: false
 signal propertiesReady()
}
