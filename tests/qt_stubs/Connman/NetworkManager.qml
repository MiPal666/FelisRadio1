import QtQuick 2.6
Item {
 property bool available: true
 property bool valid: true
 property string state: "offline"
 property bool connected: false
 property bool offlineMode: false
 property bool connectingWifi: false
 property var defaultRoute: null
 property var connectedWifi: null
 property bool servicesEnabled: false
 property bool technologiesEnabled: false
 signal availabilityChanged()
 signal servicesChanged()
 signal technologiesChanged()
}
